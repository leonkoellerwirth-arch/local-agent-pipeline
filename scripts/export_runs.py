"""CLI wrapper: export audit trails as one JSON document (for the dashboard).

The summarization logic lives in ``agent_pipeline.export`` so the CLI and the
dashboard's API server share one source of truth.

Usage (from the repo root):
    python scripts/export_runs.py --stdout
    python scripts/export_runs.py --out web/public/runs.json
    python scripts/export_runs.py --runs-dir /tmp/real_runs --stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_pipeline.export import collect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [ROOT / "runs", ROOT / "examples" / "expected-outputs"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export audit trails as JSON.")
    parser.add_argument(
        "--runs-dir", action="append", type=Path, help="Directory to scan (repeatable)."
    )
    parser.add_argument("--out", type=Path, help="Write to this file instead of stdout.")
    parser.add_argument("--stdout", action="store_true", help="Write JSON to stdout.")
    args = parser.parse_args()

    payload = json.dumps(collect(args.runs_dir or DEFAULT_DIRS), indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
