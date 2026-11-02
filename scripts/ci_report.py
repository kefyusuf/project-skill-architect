#!/usr/bin/env python3
"""Generate a read-only, bounded GitHub Actions step summary from a Git checkpoint."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from checkpoint import CheckpointError, evaluate


def safe_path(value: object) -> str:
    # Preserve valid path data while preventing markdown/terminal control sequences.
    return json.dumps(str(value)[:180], ensure_ascii=True).replace("`", "\\u0060")


def markdown_report(report: dict[str, object]) -> str:
    status = str(report["status"])
    rows = ["## Project Skill Architect — PR checkpoint", "",
            f"**Status:** `{status}`", "",
            "This is a read-only, advisory comparison. A change signal is not proof that a new skill is needed.", ""]
    signals = report.get("signals", [])
    if isinstance(signals, list):
        for signal in signals[:8]:
            if not isinstance(signal, dict):
                continue
            kind = str(signal.get("kind", "unknown"))
            paths = signal.get("paths", [])
            if isinstance(paths, list):
                rows.append(f"- **{kind}:** " + ", ".join(f"`{safe_path(p)}`" for p in paths[:12]))
    rows += ["", "**Decision:** Review against approved instructions; keep current skills if sufficient. "
             "No skills or baselines have been modified.", ""]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--since-ref", required=True)
    args = parser.parse_args(argv)
    try:
        print(markdown_report(evaluate(args.repo.resolve(), event="pr", since_ref=args.since_ref)))
    except (CheckpointError, OSError) as exc:
        print(f"Checkpoint could not complete: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
