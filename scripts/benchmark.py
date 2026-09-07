"""Run the FaceChain latency benchmark — Phase 4.

The spec's "Recommended Directory Structure" lists
`scripts/benchmark.py` and the "Performance Optimizations" section
calls for measuring the per-stage timings. This script is the
direct-CLI equivalent of `python main.py benchmark` — it prints
the same per-stage table to stdout, no Rich UI required.

Usage:
    python scripts/benchmark.py [--runs 3] [--size 320]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from facechain.benchmark import run_benchmark  # noqa: E402


def _format_table(report) -> str:
    lines: list[str] = []
    header = f"Latency benchmark (n={report.runs}, image={report.image_size[0]}x{report.image_size[1]})"
    lines.append(header)
    lines.append("-" * len(header))
    lines.append(f"{'Stage':32s} {'min':>10s} {'avg':>10s} {'max':>10s} {'n':>4s}")
    lines.append("-" * len(header))
    for stage_name, stats in report.stages.items():
        if stats["n"] == 0:
            lines.append(f"{stage_name:32s} {'N/A':>10s} {'N/A':>10s} {'N/A':>10s} {0:>4d}")
        else:
            lines.append(
                f"{stage_name:32s} "
                f"{stats['min']:>10.2f} {stats['avg']:>10.2f} {stats['max']:>10.2f} "
                f"{stats['n']:>4d}"
            )
    for note in report.notes:
        lines.append(f"# {note}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the FaceChain latency benchmark and print per-stage timings."
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of runs to aggregate (default: 3).")
    parser.add_argument("--size", type=int, default=320, help="Square image size in px (default: 320).")
    parser.add_argument("--json", action="store_true", help="Print the raw report as JSON.")
    args = parser.parse_args()

    report = run_benchmark(n=args.runs, image_size=(args.size, args.size))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return

    print(_format_table(report))


if __name__ == "__main__":
    main()
