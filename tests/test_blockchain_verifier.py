"""Tests for the Phase 3 on-chain verifier.

Drives the verifier with a fake web3 that simulates a deployed
EvidenceRegistry. Verifies the three high-level outcomes
(VERIFIED / TAMPERED / NOT_ANCHORED) plus the error paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from facechain.blockchain.client import EthereumClient
from facechain.blockchain.contract import (
    EvidenceRegistryContract,
    recompute_evidence_hash,
)
from facechain.blockchain.errors import (
    BlockchainConfigError,
    InvalidEvidenceFileError,
)
from facechain.blockchain.verifier import (
    VerificationStatus,
    verify_evidence_file,
)
from facechain.evidence.canonicalize import canonical_json, evidence_hash


# ---------------------------------------------------------------------------
# Fake web3 / contract for the verifier tests
# ---------------------------------------------------------------------------


class _FakeContract:
    """Stores whatever record the test sets, and returns it on getEvidence."""

    def __init__(self, on_chain: dict | None) -> None:
        # on_chain: { "0x" + hex64 -> (bytes32, bytes32, int, str) }
        self._on_chain = on_chain or {}
        self.calls: list[bytes] = []

    class _Functions:
        def __init__(self, parent: "_FakeContract") -> None:
            self._parent = parent

        def getEvidence(self, arg: bytes):
            outer = self

            class _Call:
                def call(self_inner):
                    outer._parent.calls.append(arg)
                    return outer._parent._on_chain.get(
                        "0x" + arg.hex(),
                        (b"\x00" * 32, b"\x00" * 32, 0, "0x" + "00" * 20),
                    )
            return _Call()

    @property
    def functions(self):
        return self._Functions(self)


class _FakeWeb3:
    def __init__(self, on_chain: dict | None) -> None:
        self._on_chain = on_chain
        self._contract = _FakeContract(on_chain)
        self.to_checksum_calls: list[str] = []

    def contract(self, address, abi):
        return self._contract

    def is_connected(self) -> bool:
        return True

    def to_checksum_address(self, addr: str) -> str:
        return addr

    def to_bytes(self, hexstr: str) -> bytes:
        return bytes.fromhex(hexstr.removeprefix("0x"))

    @property
    def eth(self):
        # The production client also uses `web3.eth.contract(...)`
        # as an alias for `web3.contract(...)`. We expose the same
        # fake contract either way.
        return self


def _client(on_chain: dict | None) -> EthereumClient:
    return EthereumClient(
        rpc_url="https://example.invalid/rpc",
        private_key="0x" + "22" * 32,
        contract_address="0x" + "33" * 20,
        chain_id=11155111,
        web3=_FakeWeb3(on_chain=on_chain),
    )


def _write_evidence(tmp_path: Path, body: dict, *, name: str = "evidence.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


def _minimal_evidence_body(extra: dict | None = None) -> dict:
    body = {
        "schemaVersion": "1.0.0-phase1",
        "search": {
            "provider": "google_cloud_vision_web_detection",
            "hadResults": True,
            "socialCandidates": [
                {"url": "https://x.com/example/status/1"},
            ],
        },
    }
    if extra:
        body.update(extra)
    # Compute the evidenceHash over the body without the hash field itself,
    # then add it. Mirrors what Phase 1's builder.py does at runtime.
    canonical = {k: v for k, v in body.items() if k != "evidenceHash"}
    body["evidenceHash"] = evidence_hash(canonical)
    return body


# ---------------------------------------------------------------------------
# recompute_evidence_hash
# ---------------------------------------------------------------------------


def test_recompute_evidence_hash_ignores_evidenceHash_field():
    body = _minimal_evidence_body()
    h1 = recompute_evidence_hash(body)
    body["evidenceHash"] = "ff" * 32
    h2 = recompute_evidence_hash(body)
    assert h1 == h2


def test_recompute_evidence_hash_matches_builder():
    """The verifier's hash MUST equal Phase 1's hash for the same body.

    NOTE: FaceChain's `evidence_hash(dict)` computes SHA-256 of the
    canonical JSON of `dict`, so both sides must call it with a dict
    (NOT with the JSON string). This test is the contract that
    keeps Phase 1, Phase 2, and Phase 3 in sync.
    """
    body = _minimal_evidence_body({"foo": "bar"})
    canonical = {k: v for k, v in body.items() if k != "evidenceHash"}
    expected = evidence_hash(canonical)
    assert recompute_evidence_hash(body) == expected


# ---------------------------------------------------------------------------
# VERIFIED
# ---------------------------------------------------------------------------


def test_verify_returns_VERIFIED_when_hash_matches_on_chain(tmp_path):
    body = _minimal_evidence_body()
    p = _write_evidence(tmp_path, body)
    expected_hash = recompute_evidence_hash(body)
    on_chain = {
        "0x" + expected_hash: (
            bytes.fromhex(expected_hash),                # evidenceHash
            b"\xab" * 32,                                # sourceHash (we don't check this in verifier)
            1_700_000_001,                               # timestamp
            "0x" + "ee" * 20,                            # submitter
        ),
    }
    report = verify_evidence_file(p, client=_client(on_chain))
    assert report.status == VerificationStatus.VERIFIED
    assert report.is_verified()
    assert not report.is_tampered()
    assert report.recomputed_evidence_hash == expected_hash
    assert report.on_chain_record is not None
    assert report.claimed_evidence_hash == body["evidenceHash"]


# ---------------------------------------------------------------------------
# NOT_ANCHORED
# ---------------------------------------------------------------------------


def test_verify_returns_NOT_ANCHORED_when_no_on_chain_record(tmp_path):
    body = _minimal_evidence_body()
    p = _write_evidence(tmp_path, body)
    # on_chain dict is empty → fake returns (zero, zero, 0, address) → not anchored.
    report = verify_evidence_file(p, client=_client(on_chain={}))
    assert report.status == VerificationStatus.NOT_ANCHORED
    assert report.on_chain_record is None
    assert report.notes and "Run `python main.py anchor`" in report.notes[0]


# ---------------------------------------------------------------------------
# TAMPERED: file edited after creation
# ---------------------------------------------------------------------------


def test_verify_returns_TAMPERED_when_local_file_modified(tmp_path):
    body = _minimal_evidence_body()
    # Tamper with the confidence field after the evidenceHash was computed.
    body["confidence"] = 0.99  # was None / not in body
    p = _write_evidence(tmp_path, body)
    # The evidenceHash in the file no longer matches the recomputed hash.
    report = verify_evidence_file(p, client=_client(on_chain={}))
    assert report.status == VerificationStatus.TAMPERED
    assert report.is_tampered()
    assert "modified" in report.notes[0].lower()


# ---------------------------------------------------------------------------
# TAMPERED: file says one hash, on chain has a different record
# ---------------------------------------------------------------------------


def test_verify_returns_TAMPERED_when_on_chain_hash_mismatch(tmp_path):
    """File is internally consistent (claimed == recomputed), but the
    on-chain record at that hash has a different evidenceHash bytes.
    This means somebody re-used the same key for a different file
    (or the chain record is corrupt) — TAMPERED."""
    body = _minimal_evidence_body()
    p = _write_evidence(tmp_path, body)
    expected_hash = recompute_evidence_hash(body)
    on_chain = {
        "0x" + expected_hash: (
            b"\x01" * 32,                                # WRONG evidenceHash bytes
            b"\x02" * 32,
            1_700_000_002,
            "0x" + "ee" * 20,
        ),
    }
    report = verify_evidence_file(p, client=_client(on_chain))
    assert report.status == VerificationStatus.TAMPERED
    assert report.on_chain_record is not None
    assert "On-chain evidenceHash" in report.notes[0]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_verify_raises_when_evidence_file_missing(tmp_path):
    with pytest.raises(InvalidEvidenceFileError):
        verify_evidence_file(tmp_path / "nope.json", client=_client({}))


def test_verify_raises_when_evidence_file_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidEvidenceFileError):
        verify_evidence_file(p, client=_client({}))


def test_verify_raises_when_blockchain_not_configured(tmp_path):
    """If client is None and no env vars are set, the default client is
    unconfigured and we should get a clean BlockchainConfigError."""
    body = _minimal_evidence_body()
    p = _write_evidence(tmp_path, body)
    # The body matches its evidenceHash, so we reach the unconfigured-
    # client branch instead of the "file modified" branch.
    from facechain.blockchain import verifier as verifier_mod
    unconfigured = EthereumClient(
        rpc_url=None, private_key=None, contract_address=None, web3=None,
    )
    with pytest.raises(BlockchainConfigError):
        verifier_mod.verify_evidence_file(p, client=unconfigured)


def test_verify_rejects_non_object_evidence_root(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(InvalidEvidenceFileError):
        verify_evidence_file(p, client=_client({}))


def test_verify_rejects_non_string_evidence_hash_field(tmp_path):
    p = _write_evidence(tmp_path, {"schemaVersion": "x", "evidenceHash": 12345})
    with pytest.raises(InvalidEvidenceFileError):
        verify_evidence_file(p, client=_client({}))
