"""Independent on-chain verification — Phase 2 placeholder.

Not implemented in Phase 1. Will allow re-deriving an evidence hash
from a local evidence.json and checking it against what's anchored on
Sepolia via EvidenceRegistryContract.
"""

from __future__ import annotations

from pathlib import Path


def verify_evidence_file(_evidence_path: Path) -> bool:
    raise NotImplementedError(
        "Blockchain verification is not implemented in Phase 1. "
        "This is a Phase 2 placeholder."
    )
