"""Phase 4 — tamper demo (spec item 20).

The spec's "Final Recommendation" describes a live tamper demo:
modify the `confidence` field in `evidence.json`, re-run the
verifier, observe TAMPERED. This module automates that flow so
judges can run it in a single command and see the
VERIFIED → TAMPERED transition with their own evidence file.

Two flavors:

1. **CLI**: `python main.py tamper-demo <evidence.json>` (offline)
   — copies the file, modifies a field, runs the local-file
   verifier check (Phase 3's `verify_evidence_file`), reports the
   transition. This works on any machine with no blockchain env.

2. **Script**: `python scripts/tamper_demo.py <evidence.json>`
   — same flow, callable directly.

The tamper demo NEVER modifies the original evidence file. It
copies to a sibling path, mutates the copy, and verifies the
copy.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# The field the spec's "Tamper Demo" example uses. We default to
# "confidence" because Phase 1's schema declares it as
# `float | None`, so any existing value can be replaced.
DEFAULT_TAMPERED_FIELD = "confidence"
DEFAULT_TAMPERED_VALUE: Any = 0.999


@dataclass(frozen=True)
class TamperDemoResult:
    """Result of running the tamper demo end-to-end."""

    source_path: Path
    tampered_path: Path
    field: str
    original_value: Any
    new_value: Any
    before_status: str
    after_status: str
    notes: list[str]

    def transitioned_to_tampered(self) -> bool:
        return self.after_status == "TAMPERED" and self.before_status != "TAMPERED"


def _read_evidence(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"Evidence file root must be a JSON object, got {type(data).__name__}"
        )
    return data


def _write_evidence(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)


def _verify_local_file(path: Path) -> str:
    """Run the local-file portion of the Phase 3 verifier and return
    a status string ('VERIFIED', 'TAMPERED', 'NOT_ANCHORED').

    The local-file check (claimed hash vs. recomputed hash) does
    NOT need blockchain env — that's the part we want to demo.
    When blockchain IS configured, the full on-chain comparison
    runs and the status reflects both.
    """
    from facechain.blockchain import verify_evidence_file
    from facechain.blockchain.errors import BlockchainConfigError
    from facechain.blockchain.verifier import VerificationStatus

    try:
        report = verify_evidence_file(path)
    except BlockchainConfigError:
        # Offline mode — re-derive just the local file check.
        from facechain.blockchain.contract import recompute_evidence_hash

        data = _read_evidence(path)
        claimed = data.get("evidenceHash")
        recomputed = recompute_evidence_hash(data)
        if claimed is None or claimed.lower() != recomputed.lower():
            return VerificationStatus.TAMPERED.value
        return VerificationStatus.VERIFIED.value

    return report.status.value


def run_tamper_demo(
    evidence_path: str | Path,
    *,
    field: str = DEFAULT_TAMPERED_FIELD,
    new_value: Any = DEFAULT_TAMPERED_VALUE,
) -> TamperDemoResult:
    """End-to-end tamper demo: verify original, copy + tamper, verify copy.

    Returns a `TamperDemoResult` describing the transition. The
    original `evidence_path` is never modified.
    """
    src = Path(evidence_path)
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Evidence file does not exist: {src}")

    notes: list[str] = []

    # 1) Verify the ORIGINAL (should be VERIFIED if the file is intact).
    before = _verify_local_file(src)
    notes.append(f"Original file verified as: {before}")

    # 2) Copy + tamper.
    tampered = src.with_suffix(src.suffix + ".tampered.json")
    shutil.copyfile(src, tampered)
    data = _read_evidence(tampered)
    original_value = data.get(field)
    data[field] = new_value
    _write_evidence(tampered, data)
    notes.append(
        f"Mutated '{field}' on the COPY at {tampered} "
        f"(original={original_value!r}, new={new_value!r}). "
        f"The original at {src} is untouched."
    )

    # 3) Verify the TAMPERED COPY (should be TAMPERED).
    after = _verify_local_file(tampered)
    notes.append(f"Tampered copy verified as: {after}")

    return TamperDemoResult(
        source_path=src,
        tampered_path=tampered,
        field=field,
        original_value=original_value,
        new_value=new_value,
        before_status=before,
        after_status=after,
        notes=notes,
    )
