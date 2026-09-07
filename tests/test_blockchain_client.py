"""Tests for the Phase 3 EthereumClient.

These tests never connect to a real network. They construct
EthereumClient with `web3=` injected fakes, and verify:

* Configuration detection (which env vars are present).
* Lazy web3 / account creation.
* `connection_info` reports the correct values.
* The injected fake web3 is the one actually used (no fallback
  HTTP provider is ever instantiated).
"""

from __future__ import annotations

import pytest

from facechain.blockchain.client import EVIDENCE_REGISTRY_ABI, EthereumClient
from facechain.blockchain.errors import BlockchainConfigError


class _FakeAccount:
    def __init__(self, address: str = "0x" + "11" * 20) -> None:
        self.address = address


class _FakeWeb3:
    def __init__(self, *, connected: bool = True, address: str | None = None) -> None:
        self._connected = connected
        self._address = address or "0x" + "11" * 20

    def is_connected(self) -> bool:
        return self._connected

    def to_checksum_address(self, addr: str) -> str:
        return addr  # pretend everything is already checksummed

    def to_bytes(self, hexstr: str) -> bytes:
        return bytes.fromhex(hexstr.removeprefix("0x"))


def test_client_reports_not_configured_when_all_settings_missing():
    """`Settings` is a frozen dataclass so we can't monkeypatch its
    attributes; instead we pass explicit `None`s to the constructor."""
    client = EthereumClient(
        rpc_url=None, private_key=None, contract_address=None,
        web3=_FakeWeb3(),
    )
    assert client.is_fully_configured() is False
    with pytest.raises(BlockchainConfigError) as exc:
        client.require_fully_configured()
    msg = str(exc.value)
    assert "SEPOLIA_RPC_URL" in msg
    assert "BLOCKCHAIN_PRIVATE_KEY" in msg
    assert "CONTRACT_ADDRESS" in msg


def test_client_reports_configured_when_all_settings_present():
    client = EthereumClient(
        rpc_url="https://example.invalid/rpc",
        private_key="0x" + "22" * 32,
        contract_address="0x" + "33" * 20,
        chain_id=11155111,
        web3=_FakeWeb3(),
    )
    assert client.is_fully_configured() is True
    # require_fully_configured should not raise.
    client.require_fully_configured()


def test_client_partial_configuration_raises(monkeypatch):
    client = EthereumClient(
        rpc_url="https://example.invalid/rpc",
        private_key=None,
        contract_address="0x" + "33" * 20,
        web3=_FakeWeb3(),
    )
    assert client.is_fully_configured() is False
    with pytest.raises(BlockchainConfigError) as exc:
        client.require_fully_configured()
    assert "BLOCKCHAIN_PRIVATE_KEY" in str(exc.value)


def test_client_uses_injected_web3_without_connecting(monkeypatch):
    """The injected fake web3 should be used as-is — no HTTP provider
    should ever be constructed when the caller passes `web3=`."""
    fake = _FakeWeb3(connected=True)
    client = EthereumClient(
        rpc_url="https://should-never-be-used.invalid",
        private_key="0x" + "22" * 32,
        contract_address="0x" + "33" * 20,
        web3=fake,
    )
    assert client.web3 is fake
    assert client.is_connected() is True


def test_client_connection_info_includes_all_fields():
    """`submitter_address` is derived from the private key via
    eth_account, NOT from the injected fake web3. The address is
    deterministic for a given private key."""
    from eth_account import Account

    client = EthereumClient(
        rpc_url="https://example.invalid/rpc",
        private_key="0x" + "22" * 32,
        contract_address="0x" + "33" * 20,
        chain_id=11155111,
        web3=_FakeWeb3(address="0x" + "44" * 20),
    )
    info = client.connection_info()
    assert info.rpc_url == "https://example.invalid/rpc"
    assert info.chain_id == 11155111
    assert info.submitter_address == Account.from_key("0x" + "22" * 32).address
    assert info.contract_address == "0x" + "33" * 20
    # And the fake web3's address is NOT used.
    assert info.submitter_address != "0x" + "44" * 20


def test_client_abi_has_register_and_get():
    """The bundled ABI should be sufficient for both our contract calls."""
    names = {entry["name"] for entry in EVIDENCE_REGISTRY_ABI}
    assert "registerEvidence" in names
    assert "getEvidence" in names
