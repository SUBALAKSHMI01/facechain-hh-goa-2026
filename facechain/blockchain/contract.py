"""EvidenceRegistry contract interaction — Phase 2 placeholder.

Not implemented in Phase 1. Will wrap calls to the deployed
EvidenceRegistry.sol contract (see contracts/EvidenceRegistry.sol)
once it exists.
"""

from __future__ import annotations


class EvidenceRegistryContract:
    """Placeholder for the deployed EvidenceRegistry contract wrapper. Phase 2."""

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "Blockchain functionality is not implemented in Phase 1. "
            "EvidenceRegistryContract is a Phase 2 placeholder."
        )

    def anchor_evidence_hash(self, evidence_hash: str) -> str:
        raise NotImplementedError("Phase 2: not implemented yet.")

    def get_anchored_record(self, evidence_hash: str):
        raise NotImplementedError("Phase 2: not implemented yet.")
