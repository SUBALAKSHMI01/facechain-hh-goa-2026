"""Phase 3 — blockchain-specific exception types.

Kept in a dedicated module so both the live Sepolia path and the
offline verification path can raise the same, narrow, catchable errors
without importing web3 (which would force the offline path to pull in
the full web3 stack).
"""

from __future__ import annotations


class BlockchainError(Exception):
    """Base class for Phase 3 blockchain errors with a human-readable message."""


class BlockchainConfigError(BlockchainError):
    """Raised when a blockchain command is invoked without the required
    env vars (RPC URL / private key / contract address)."""


class BlockchainTransactionError(BlockchainError):
    """Raised when a Sepolia transaction fails to submit, times out, or
    is reverted by the contract."""


class EvidenceNotAnchoredError(BlockchainError):
    """Raised by `verify_evidence_file` when the evidence hash has no
    on-chain record yet (the file was never anchored on Sepolia, or
    the hash on the file does not match what is on-chain)."""


class InvalidEvidenceFileError(BlockchainError):
    """Raised when a file passed to `verify_evidence_file` is not a
    valid, hashable FaceChain evidence file."""
