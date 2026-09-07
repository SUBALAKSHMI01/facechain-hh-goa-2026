"""Ethereum Sepolia client — Phase 2 placeholder.

Not implemented in Phase 1. This interface will wrap a web3.py
connection (RPC URL, signing key management) once blockchain
anchoring is implemented.
"""

from __future__ import annotations


class EthereumClient:
    """Placeholder for a Sepolia-connected web3 client. Phase 2."""

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "Blockchain functionality is not implemented in Phase 1. "
            "EthereumClient is a Phase 2 placeholder."
        )
