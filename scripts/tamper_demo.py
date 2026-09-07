"""Run the FaceChain tamper demo — Phase 4.

Direct-CLI equivalent of `python main.py tamper-demo <evidence.json>`.
Exits 0 on a clean VERIFIED → TAMPERED transition, non-zero otherwise.

Usage:
    python scripts/tamper_demo.py <evidence.json> [--field confidence] [--value 0.999]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from facechain.tamper_demo import run_tamper_demo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the FaceChain live tamper demo: verify → mutate → re-verify."
    )
    parser.add_argument("evidence", type=Path, help="Path to a FaceChain evidence.json.")
    parser.add_argument("--field", default="confidence", help="Field to mutate (default: confidence).")
    parser.add_argument("--value", default="0.999", help="New value (parsed as JSON if possible).")
    args = parser.parse_args()

    if not args.evidence.exists() or not args.evidence.is_file():
        print(f"✗ Evidence file does not exist: {args.evidence}", file=sys.stderr)
        sys.exit(1)

    try:
        parsed_value: object = json.loads(args.value)
    except json.JSONDecodeError:
        parsed_value = args.value

    try:
        result = run_tamper_demo(args.evidence, field=args.field, new_value=parsed_value)
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Original file:  {result.source_path}")
    print(f"  before verify: {result.before_status}")
    print(f"Tampered copy:  {result.tampered_path}")
    print(f"  mutated '{result.field}': {result.original_value!r} → {result.new_value!r}")
    print(f"  after verify:  {result.after_status}")
    print()
    for note in result.notes:
        print(f"  • {note}")

    if result.transitioned_to_tampered():
        print("\n✓ Tamper detected. VERIFIED → TAMPERED transition observed.")
        sys.exit(0)
    if result.before_status == "TAMPERED":
        print(
            "\n! The original file was already TAMPERED. Run on an un-modified "
            "evidence file to see the full transition.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(
        f"\n✗ The tamper was not detected. Status: {result.before_status} → {result.after_status}.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
