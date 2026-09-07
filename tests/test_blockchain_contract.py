"""Tests for the Phase 3 EvidenceRegistryContract.

Uses a hand-rolled fake web3 + fake contract that mimics the
surface our code actually touches:

* web3.eth.contract(address=..., abi=...)
* contract.functions.registerEvidence(...).build_transaction({...})
* account.sign_transaction(tx) → .raw_transaction
* web3.eth.send_raw_transaction(...) → tx_hash
* web3.eth.wait_for_transaction_receipt(tx_hash) → receipt
* web3.eth.get_transaction_count(addr)
* web3.eth.gas_price
* contract.functions.getEvidence(...).call() → (bytes32, bytes32, uint, addr)

This avoids depending on `eth-tester` while still exercising the
real on-chain call flow end-to-end (build → sign → send → wait →
re-read).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from facechain.blockchain.client import EthereumClient
from facechain.blockchain.contract import (
    BYTES32_HEX_LEN,
    EvidenceRegistryContract,
    OnChainRecord,
)
from facechain.blockchain.errors import (
    BlockchainConfigError,
    BlockchainTransactionError,
    InvalidEvidenceFileError,
)
from facechain.search.normalizer import normalize_url
from facechain.vision.hashing import sha256_bytes


# ---------------------------------------------------------------------------
# Fake web3 / fake contract
# ---------------------------------------------------------------------------


_SENT_TX_LOG: list[bytes] = []
_SUBMITTED_TRANSACTIONS: dict[bytes, dict] = {}


class _FakeFunction:
    def __init__(self, name: str, parent: "_FakeContract") -> None:
        self._name = name
        self._parent = parent

    def __call__(self, *args, **kwargs):
        # recordEvidence / getEvidence both accept one or two bytes32 args
        return _FakeCall(self._name, args, self._parent)


class _FakeCall:
    def __init__(self, name: str, args, parent: "_FakeContract") -> None:
        self._name = name
        self._args = args
        self._parent = parent

    def build_transaction(self, tx: dict) -> dict:
        # Real web3.py does NOT add _name/_args; we keep those only
        # in the parent so tests can introspect them, and return the
        # tx dict verbatim so sign_transaction sees exactly what
        # production code would have built.
        self._parent.last_build_transaction_args = dict(tx)
        self._parent.last_build_transaction_name = self._name
        self._parent.last_build_transaction_args_captured = dict(tx)
        # Record the call args so the fake eth module can update
        # the on-chain "ledger" after a successful tx (mimicking
        # what the real contract would do).
        self._parent.last_call_args = list(self._args)
        return tx

    def call(self):
        if self._name == "getEvidence":
            # Look up the just-anchored record by its evidenceHash bytes.
            key = "0x" + bytes(self._args[0]).hex()
            if key in self._parent.on_chain:
                return self._parent.on_chain[key]
            # Fall back to the explicit per-test `next_call_return`.
            return self._parent.next_call_return
        # Return whatever the fake's `next_call_return` says.
        return self._parent.next_call_return


class _FakeContract:
    def __init__(self) -> None:
        self.last_build_transaction_args: dict | None = None
        self.last_build_transaction_args_captured: dict | None = None
        self.last_build_transaction_name: str | None = None
        self.last_call_args: list = []
        self.next_call_return: tuple = (
            b"\x00" * 32, b"\x00" * 32, 0, "0x" + "00" * 20,
        )
        self.on_chain: dict[str, tuple] = {}
        self.functions = self  # so .functions.registerEvidence(...) works

    def registerEvidence(self, *args):
        return _FakeCall("registerEvidence", args, self)

    def getEvidence(self, *args):
        return _FakeCall("getEvidence", args, self)

    def record_register(self, evidence_hash_bytes: bytes, source_hash_bytes: bytes,
                        submitter: str, timestamp: int = 1_700_000_000) -> None:
        """Simulate the contract writing a record after a successful tx."""
        key = "0x" + evidence_hash_bytes.hex()
        self.on_chain[key] = (
            evidence_hash_bytes,
            source_hash_bytes,
            timestamp,
            submitter,
        )


class _FakeSigned:
    def __init__(self, raw: bytes) -> None:
        self.raw_transaction = raw


class _FakeAccount:
    def __init__(self, address: str = "0x" + "11" * 20) -> None:
        self.address = address
        self._nonce = 0
        self.signed_txs: list[dict] = []

    def sign_transaction(self, tx: dict) -> _FakeSigned:
        self.signed_txs.append(dict(tx))
        # Use a constant raw bytes so the test can assert on it; we
        # don't need the function name here because the test inspects
        # `last_build_transaction_name` separately.
        return _FakeSigned(raw=b"signed-raw-tx")


class _FakeWeb3:
    def __init__(self, *, receipt_status: int = 1, account: _FakeAccount | None = None) -> None:
        self._receipt_status = receipt_status
        self._account = account or _FakeAccount()
        self._contract = _FakeContract()
        self._eth = _FakeEthModule(self)
        self.to_checksum_calls: list[str] = []

    # web3 surface used by client.py / contract.py
    def is_connected(self) -> bool:
        return True

    def to_checksum_address(self, addr: str) -> str:
        self.to_checksum_calls.append(addr)
        return addr

    def to_bytes(self, hexstr: str) -> bytes:
        return bytes.fromhex(hexstr.removeprefix("0x"))

    def contract(self, address, abi):
        return self._contract

    @property
    def eth(self) -> "_FakeEthModule":
        return self._eth


class _FakeEthModule:
    """Subset of web3.eth surface used by client.contract() and
    contract.register_evidence."""

    def __init__(self, parent: _FakeWeb3) -> None:
        self._parent = parent

    def contract(self, address, abi):
        return self._parent._contract

    def get_transaction_count(self, addr: str) -> int:
        return 0

    @property
    def gas_price(self) -> int:
        return 1_000_000_000

    def send_raw_transaction(self, raw: bytes) -> bytes:
        from eth_account import Account

        _SENT_TX_LOG.append(raw)
        tx_hash = sha256_bytes(raw).encode("ascii")[:32]
        _SUBMITTED_TRANSACTIONS[tx_hash] = {
            "raw": raw,
            "blockNumber": 12_345,
        }
        # Simulate the contract persisting the record on success.
        # Submitter is the real address derived from the same
        # private key the production code used, so the round-trip
        # is consistent.
        last_args = self._parent._contract.last_call_args
        if len(last_args) >= 2:
            submitter = Account.from_key("0x" + "22" * 32).address
            self._parent._contract.record_register(
                evidence_hash_bytes=last_args[0],
                source_hash_bytes=last_args[1],
                submitter=submitter,
            )
        return tx_hash

    def wait_for_transaction_receipt(self, tx_hash: bytes, timeout: int):
        assert tx_hash in _SUBMITTED_TRANSACTIONS
        info = _SUBMITTED_TRANSACTIONS[tx_hash]
        return {
            "status": self._parent._receipt_status,
            "blockNumber": info["blockNumber"],
            "contractAddress": "0x" + "ab" * 20,
        }


def _make_client(receipt_status: int = 1) -> tuple[EthereumClient, _FakeWeb3]:
    fake = _FakeWeb3(receipt_status=receipt_status)
    client = EthereumClient(
        rpc_url="https://example.invalid/rpc",
        private_key="0x" + "22" * 32,
        contract_address="0x" + "33" * 20,
        chain_id=11155111,
        web3=fake,
    )
    return client, fake


@pytest.fixture(autouse=True)
def _reset_log():
    _SENT_TX_LOG.clear()
    _SUBMITTED_TRANSACTIONS.clear()
    yield
    _SENT_TX_LOG.clear()
    _SUBMITTED_TRANSACTIONS.clear()


# ---------------------------------------------------------------------------
# hex_to_bytes32
# ---------------------------------------------------------------------------


def test_hex_to_bytes32_accepts_64_char_hex():
    h = "a" * 64
    assert EvidenceRegistryContract.hex_to_bytes32(h) == "0x" + h


def test_hex_to_bytes32_accepts_0x_prefixed_hex():
    h = "abcdef" * 10 + "abcd"
    assert EvidenceRegistryContract.hex_to_bytes32("0x" + h) == "0x" + h


def test_hex_to_bytes32_rejects_wrong_length():
    with pytest.raises(InvalidEvidenceFileError):
        EvidenceRegistryContract.hex_to_bytes32("a" * 63)
    with pytest.raises(InvalidEvidenceFileError):
        EvidenceRegistryContract.hex_to_bytes32("a" * 65)


def test_hex_to_bytes32_rejects_non_hex():
    with pytest.raises(InvalidEvidenceFileError):
        EvidenceRegistryContract.hex_to_bytes32("z" * 64)


def test_hex_to_bytes32_rejects_non_string():
    with pytest.raises(InvalidEvidenceFileError):
        EvidenceRegistryContract.hex_to_bytes32(12345)  # type: ignore[arg-type]


def test_bytes32_hex_len_is_64():
    assert BYTES32_HEX_LEN == 64


# ---------------------------------------------------------------------------
# source_hash_for_url
# ---------------------------------------------------------------------------


def test_source_hash_for_url_normalizes_before_hashing():
    """Two URLs that differ only in www./case/trailing slash should
    hash to the same sourceHash."""
    url1 = "https://www.Instagram.com/someone/"
    url2 = "https://instagram.com/someone"
    h1 = EvidenceRegistryContract.source_hash_for_url(url1)
    h2 = EvidenceRegistryContract.source_hash_for_url(url2)
    assert h1 == h2


def test_source_hash_for_url_different_urls_different_hashes():
    h1 = EvidenceRegistryContract.source_hash_for_url("https://x.com/a")
    h2 = EvidenceRegistryContract.source_hash_for_url("https://x.com/b")
    assert h1 != h2


def test_source_hash_for_url_empty_string_still_hashes():
    """Even an empty URL produces a deterministic hash (SHA-256 of '')."""
    h = EvidenceRegistryContract.source_hash_for_url("")
    assert len(h) == 64
    assert h == sha256_bytes(b"")


# ---------------------------------------------------------------------------
# get_evidence
# ---------------------------------------------------------------------------


def test_get_evidence_returns_none_when_on_chain_timestamp_is_zero():
    client, fake = _make_client()
    contract = EvidenceRegistryContract(client)
    result = contract.get_evidence("a" * 64)
    assert result is None


def test_get_evidence_returns_record_when_present():
    client, fake = _make_client()
    fake._contract.next_call_return = (
        b"\x01" * 32,            # evidenceHash
        b"\x02" * 32,            # sourceHash
        1_700_000_000,           # timestamp
        "0x" + "ee" * 20,        # submitter
    )
    contract = EvidenceRegistryContract(client)
    result = contract.get_evidence("a" * 64)
    assert isinstance(result, OnChainRecord)
    assert result.evidence_hash == "0x" + "01" * 32
    assert result.source_hash == "0x" + "02" * 32
    assert result.timestamp == 1_700_000_000
    assert result.submitter == "0x" + "ee" * 20


def test_get_evidence_raises_when_not_configured():
    client = EthereumClient(
        rpc_url=None, private_key=None, contract_address=None,
        web3=_FakeWeb3(),
    )
    contract = EvidenceRegistryContract(client)
    with pytest.raises(BlockchainConfigError):
        contract.get_evidence("a" * 64)


# ---------------------------------------------------------------------------
# register_evidence
# ---------------------------------------------------------------------------


def test_register_evidence_builds_signs_and_sends_transaction():
    from eth_account import Account

    client, fake = _make_client()
    contract = EvidenceRegistryContract(client)

    evidence_hex = "b" * 64
    source_url = "https://x.com/example/status/123"
    expected_source_hash = EvidenceRegistryContract.source_hash_for_url(
        normalize_url(source_url)
    )
    expected_submitter = Account.from_key("0x" + "22" * 32).address

    result = contract.register_evidence(evidence_hex, source_url)

    # 1) The fake was actually asked to build a registerEvidence tx.
    assert fake._contract.last_build_transaction_name == "registerEvidence"
    built = fake._contract.last_build_transaction_args
    assert built["chainId"] == 11155111
    assert built["from"] == expected_submitter
    assert built["gas"] == 200_000

    # 2) A signed raw tx was sent and we got back its hash.
    # The real eth_account.Account.from_key signs the tx; the fake's
    # web3 records the signed bytes in _SENT_TX_LOG so we can assert
    # that exactly one transaction was sent.
    assert len(_SENT_TX_LOG) == 1
    assert isinstance(_SENT_TX_LOG[0], (bytes, bytearray))
    assert result.transaction_hash.startswith("0x")
    assert result.block_number == 12_345
    assert result.evidence_hash == "0x" + evidence_hex
    assert result.source_hash == "0x" + expected_source_hash
    # The fake's record_register wrote a non-zero timestamp (1_700_000_000).
    assert result.timestamp == 1_700_000_000
    assert result.submitter == expected_submitter


def test_register_evidence_raises_on_reverted_receipt():
    client, fake = _make_client(receipt_status=0)
    contract = EvidenceRegistryContract(client)
    with pytest.raises(BlockchainTransactionError) as exc:
        contract.register_evidence("c" * 64, "https://x.com/a")
    assert "reverted" in str(exc.value).lower()


def test_register_evidence_raises_when_not_configured():
    client = EthereumClient(
        rpc_url=None, private_key=None, contract_address=None,
        web3=_FakeWeb3(),
    )
    contract = EvidenceRegistryContract(client)
    with pytest.raises(BlockchainConfigError):
        contract.register_evidence("d" * 64, "https://x.com/a")


def test_register_evidence_rejects_malformed_evidence_hash():
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    with pytest.raises(InvalidEvidenceFileError):
        contract.register_evidence("not-hex", "https://x.com/a")


# ---------------------------------------------------------------------------
# register_evidence_from_file
# ---------------------------------------------------------------------------


def _write_phase1_evidence(tmp_path: Path) -> Path:
    p = tmp_path / "evidence.json"
    p.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0-phase1",
                "evidenceHash": "0a" * 32,
                "search": {
                    "socialCandidates": [
                        {"url": "https://x.com/example/status/1"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return p


def test_register_evidence_from_file_reads_evidence_hash_and_url(tmp_path):
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    p = _write_phase1_evidence(tmp_path)
    result = contract.register_evidence_from_file(p)
    assert result.evidence_hash == "0x" + "0a" * 32
    expected_source_hash = EvidenceRegistryContract.source_hash_for_url(
        normalize_url("https://x.com/example/status/1")
    )
    assert result.source_hash == "0x" + expected_source_hash


def test_register_evidence_from_file_missing_file_raises(tmp_path):
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    with pytest.raises(InvalidEvidenceFileError):
        contract.register_evidence_from_file(tmp_path / "nope.json")


def test_register_evidence_from_file_invalid_json_raises(tmp_path):
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidEvidenceFileError):
        contract.register_evidence_from_file(p)


def test_register_evidence_from_file_missing_evidence_hash_field_raises(tmp_path):
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    p = tmp_path / "no_hash.json"
    p.write_text(json.dumps({"search": {}}), encoding="utf-8")
    with pytest.raises(InvalidEvidenceFileError) as exc:
        contract.register_evidence_from_file(p)
    assert "evidenceHash" in str(exc.value)


def test_register_evidence_from_file_no_social_candidates_still_anchors(tmp_path):
    """A file with no social candidates anchors with sourceHash(SHA256 of '')."""
    client, _ = _make_client()
    contract = EvidenceRegistryContract(client)
    p = tmp_path / "no_social.json"
    p.write_text(
        json.dumps({"evidenceHash": "cd" * 32, "search": {}}),
        encoding="utf-8",
    )
    result = contract.register_evidence_from_file(p)
    expected_source_hash = EvidenceRegistryContract.source_hash_for_url("")
    assert result.source_hash == "0x" + expected_source_hash
