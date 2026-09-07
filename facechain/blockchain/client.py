"""Ethereum Sepolia client — Phase 3.

Thin wrapper around web3.py that:

* holds an HTTP provider pointed at the Sepolia RPC URL,
* holds an eth-account `Account` loaded from `BLOCKCHAIN_PRIVATE_KEY`,
* exposes the connected chain id and submitter address,
* exposes the contract instance once `CONTRACT_ADDRESS` is set.

The web3 instance is *injectable* via the `web3=` kwarg so unit tests
can pass a `FakeWeb3` without ever touching the network. Production
code lets `EthereumClient` construct the real provider itself.

This module never logs or prints the private key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from facechain.blockchain.errors import BlockchainConfigError
from facechain.config import settings


# Minimal ABI for the methods we call. Defining it here (rather than
# fetching it from a compiled artifact) keeps the contract surface
# stable across deploy paths — Remix, Hardhat, solcx all produce a
# contract with this exact public interface.
EVIDENCE_REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
            {"internalType": "bytes32", "name": "sourceHash", "type": "bytes32"},
        ],
        "name": "registerEvidence",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"}],
        "name": "getEvidence",
        "outputs": [
            {"internalType": "bytes32", "name": "evidenceHashOut", "type": "bytes32"},
            {"internalType": "bytes32", "name": "sourceHashOut", "type": "bytes32"},
            {"internalType": "uint256", "name": "timestampOut", "type": "uint256"},
            {"internalType": "address", "name": "submitterOut", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True)
class ConnectionInfo:
    """Lightweight, serializable summary of the connection."""

    rpc_url: str
    chain_id: int
    submitter_address: str
    contract_address: str | None


class EthereumClient:
    """Sepolia web3.py client.

    Parameters
    ----------
    rpc_url, private_key, contract_address, chain_id:
        Override individual settings (mainly used by tests and by the
        deploy script). Default to values from facechain.config.settings.
    web3:
        Optional pre-built web3.Web3 instance. If provided, the client
        uses it verbatim and does NOT make any network connection. This
        is the test seam — production code does not pass this arg.
    """

    def __init__(
        self,
        rpc_url: str | None = None,
        private_key: str | None = None,
        contract_address: str | None = None,
        chain_id: int | None = None,
        *,
        web3: Any | None = None,
    ) -> None:
        self._rpc_url = rpc_url or settings.sepolia_rpc_url
        self._private_key = private_key or settings.blockchain_private_key
        self._contract_address = contract_address or settings.contract_address
        self._chain_id = chain_id if chain_id is not None else settings.chain_id
        self._injected_web3 = web3
        self._account: Any | None = None

    # -- Configuration checks -----------------------------------------

    def is_fully_configured(self) -> bool:
        """True iff submit/verify can run end-to-end against a live chain."""
        return bool(self._rpc_url and self._private_key and self._contract_address)

    def require_fully_configured(self) -> None:
        if not self.is_fully_configured():
            missing = []
            if not self._rpc_url:
                missing.append("SEPOLIA_RPC_URL")
            if not self._private_key:
                missing.append("BLOCKCHAIN_PRIVATE_KEY")
            if not self._contract_address:
                missing.append("CONTRACT_ADDRESS")
            raise BlockchainConfigError(
                "Blockchain is not configured. Set the following env vars: "
                + ", ".join(missing)
            )

    # -- Lazy initialization ------------------------------------------

    @property
    def web3(self) -> Any:
        """Return the web3.Web3 instance, creating it on first use."""
        if self._injected_web3 is not None:
            return self._injected_web3
        # Lazy import so importing this module never requires web3.py
        # to be installed at import time of unrelated features.
        from web3 import Web3

        if not self._rpc_url:
            raise BlockchainConfigError("SEPOLIA_RPC_URL is not set.")
        return Web3(Web3.HTTPProvider(self._rpc_url))

    @property
    def account(self) -> Any:
        """Return the eth_account.Account derived from the private key."""
        if self._account is not None:
            return self._account
        if not self._private_key:
            raise BlockchainConfigError("BLOCKCHAIN_PRIVATE_KEY is not set.")
        from eth_account import Account

        self._account = Account.from_key(self._private_key)
        return self._account

    @property
    def submitter_address(self) -> str:
        return self.account.address

    @property
    def contract_address_str(self) -> str | None:
        return self._contract_address

    @property
    def chain_id_int(self) -> int:
        return self._chain_id

    def connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            rpc_url=self._rpc_url or "",
            chain_id=self._chain_id,
            submitter_address=self.account.address,
            contract_address=self._contract_address,
        )

    def contract(self) -> Any:
        """Return a web3 contract instance bound to the deployed registry."""
        if not self._contract_address:
            raise BlockchainConfigError("CONTRACT_ADDRESS is not set.")
        return self.web3.eth.contract(
            address=self.web3.to_checksum_address(self._contract_address),
            abi=EVIDENCE_REGISTRY_ABI,
        )

    # -- Network liveness (best-effort, used for nicer error messages) -

    def is_connected(self) -> bool:
        """Return True if the underlying web3 provider answers."""
        try:
            return bool(self.web3.is_connected())
        except Exception:
            return False
