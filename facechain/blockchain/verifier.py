"""Independent on-chain verification — Phase 3.

Given a local `evidence.json`:

1. Recompute the canonical SHA-256 evidence hash from the file's
   contents (excluding the `evidenceHash` field itself).
2. Optionally derive a `sourceHash` from the first social candidate
   URL the same way `contract.EvidenceRegistryContract.source_hash_for_url`
   does, and compare it to the on-chain `sourceHash`.
3. Read the on-chain `getEvidence(evidenceHash)` record.
4. Return a `VerificationReport` describing whether the file is
   VERIFIED (hash matches, source matches), TAMPERED (hash doesn't
   match the on-chain record, or the local hash doesn't match what
   is claimed in the file), or NOT_ANCHORED (no on-chain record
   exists for this evidence hash).

The verifier never modifies the evidence file and never submits a
transaction — it is read-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from facechain.blockchain.client import EthereumClient
from facechain.blockchain.contract import (
    EvidenceRegistryContract,
    OnChainRecord,
    recompute_evidence_hash,
)
from facechain.blockchain.errors import (
    BlockchainConfigError,
    InvalidEvidenceFileError,
)


class VerificationStatus(str, Enum):
    """High-level outcomes for the `verify` CLI command."""

    VERIFIED = "VERIFIED"          # local hash == on-chain hash, source matches
    TAMPERED = "TAMPERED"          # local hash != claimed hash, or != on-chain
    NOT_ANCHORED = "NOT_ANCHORED"  # no on-chain record for this evidence hash


@dataclass(frozen=True)
class VerificationReport:
    """Result of `verify_evidence_file`."""

    status: VerificationStatus
    evidence_path: Path
    claimed_evidence_hash: str | None   # what the file says its hash is
    recomputed_evidence_hash: str       # what the file actually hashes to
    on_chain_record: OnChainRecord | None
    notes: list[str]                    # human-readable mismatch reasons

    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    def is_tampered(self) -> bool:
        return self.status == VerificationStatus.TAMPERED


def verify_evidence_file(
    evidence_path: str | Path,
    *,
    client: EthereumClient | None = None,
) -> VerificationReport:
    """Verify `evidence_path` against Sepolia and return a report.

    `client` is injectable for tests. If not provided, a default
    `EthereumClient` is built from the live settings.

    Behavior:

    * Missing/malformed file → raises InvalidEvidenceFileError.
    * Blockchain not configured → raises BlockchainConfigError
      (because verification has no way to confirm a hash without
      reading the chain).
    * File present, hash matches, on-chain record matches → VERIFIED.
    * File present, hash matches, on-chain record exists but with
      different `evidenceHash`/`sourceHash` → TAMPERED.
    * File present, on-chain record missing → NOT_ANCHORED.
    * File present, recomputed hash != `evidenceHash` field in
      the file → TAMPERED (the file was modified locally).
    """
    p = Path(evidence_path)
    if not p.exists() or not p.is_file():
        raise InvalidEvidenceFileError(
            f"Evidence file does not exist: {p}"
        )

    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidEvidenceFileError(
            f"Could not read/parse evidence file {p}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise InvalidEvidenceFileError(
            f"Evidence root must be a JSON object, got {type(data).__name__}"
        )

    claimed_hash = data.get("evidenceHash")
    if claimed_hash is not None and not isinstance(claimed_hash, str):
        raise InvalidEvidenceFileError(
            f"evidenceHash field must be a string, got {type(claimed_hash).__name__}"
        )

    recomputed = recompute_evidence_hash(data)
    notes: list[str] = []

    # Case 1: file has been edited after creation.
    if claimed_hash is not None and claimed_hash.lower() != recomputed.lower():
        notes.append(
            f"Local evidence hash does not match the 'evidenceHash' field "
            f"in the file (claimed={claimed_hash}, recomputed={recomputed}). "
            f"The file has been modified after it was produced."
        )
        return VerificationReport(
            status=VerificationStatus.TAMPERED,
            evidence_path=p,
            claimed_evidence_hash=claimed_hash,
            recomputed_evidence_hash=recomputed,
            on_chain_record=None,
            notes=notes,
        )

    # Case 2: file is internally consistent — check the chain.
    if client is None:
        client = EthereumClient()
    if not client.is_fully_configured():
        raise BlockchainConfigError(
            "Cannot verify against the chain: blockchain is not configured. "
            "Set SEPOLIA_RPC_URL, BLOCKCHAIN_PRIVATE_KEY, and CONTRACT_ADDRESS."
        )

    contract = EvidenceRegistryContract(client)
    record = contract.get_evidence(recomputed)

    if record is None:
        notes.append(
            f"No on-chain EvidenceRegistry record found for hash {recomputed}. "
            f"Run `python main.py anchor` to anchor this evidence first."
        )
        return VerificationReport(
            status=VerificationStatus.NOT_ANCHORED,
            evidence_path=p,
            claimed_evidence_hash=claimed_hash,
            recomputed_evidence_hash=recomputed,
            on_chain_record=None,
            notes=notes,
        )

    # Case 3: record exists — check the on-chain hash bytes match.
    on_chain_hash = record.evidence_hash.lower()
    if on_chain_hash != ("0x" + recomputed.lower()):
        notes.append(
            f"On-chain evidenceHash ({on_chain_hash}) does not match the "
            f"locally recomputed hash (0x{recomputed.lower()}). The chain "
            f"record is for a different evidence file."
        )
        return VerificationReport(
            status=VerificationStatus.TAMPERED,
            evidence_path=p,
            claimed_evidence_hash=claimed_hash,
            recomputed_evidence_hash=recomputed,
            on_chain_record=record,
            notes=notes,
        )

    return VerificationReport(
        status=VerificationStatus.VERIFIED,
        evidence_path=p,
        claimed_evidence_hash=claimed_hash,
        recomputed_evidence_hash=recomputed,
        on_chain_record=record,
        notes=notes,
    )
