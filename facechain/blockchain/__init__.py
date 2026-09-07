"""Blockchain anchoring — Phase 3 (Sepolia).

Phase 3 implements:

* `EthereumClient` — a thin web3.py wrapper pointed at Sepolia, with
  an injectable `web3=` for tests.
* `EvidenceRegistryContract` — high-level register/get operations
  against the deployed `EvidenceRegistry.sol` contract.
* `verifier.verify_evidence_file` — read-only re-derivation of the
  evidence hash from a local file and comparison with the on-chain
  record, returning VERIFIED / TAMPERED / NOT_ANCHORED.

Only cryptographic commitments (`evidenceHash`, `sourceHash`) ever
leave the machine — the evidence file itself stays off-chain.

The blockchain layer is purely additive: Phase 1 and Phase 2 keep
working unchanged without any blockchain env vars.
"""

from facechain.blockchain.client import (
    EVIDENCE_REGISTRY_ABI,
    ConnectionInfo,
    EthereumClient,
)
from facechain.blockchain.contract import (
    AnchorResult,
    EvidenceRegistryContract,
    OnChainRecord,
    recompute_evidence_hash,
)
from facechain.blockchain.errors import (
    BlockchainConfigError,
    BlockchainError,
    BlockchainTransactionError,
    EvidenceNotAnchoredError,
    InvalidEvidenceFileError,
)
from facechain.blockchain.verifier import (
    VerificationReport,
    VerificationStatus,
    verify_evidence_file,
)

__all__ = [
    "AnchorResult",
    "BlockchainConfigError",
    "BlockchainError",
    "BlockchainTransactionError",
    "ConnectionInfo",
    "EVIDENCE_REGISTRY_ABI",
    "EvidenceNotAnchoredError",
    "EvidenceRegistryContract",
    "EthereumClient",
    "InvalidEvidenceFileError",
    "OnChainRecord",
    "VerificationReport",
    "VerificationStatus",
    "recompute_evidence_hash",
    "verify_evidence_file",
]
