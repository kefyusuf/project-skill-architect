#!/usr/bin/env python3
"""Read-only, evidence-aware Skill effectiveness evaluation (v7).

Consumes a bounded, de-identified scenario suite. No transcripts, prompts,
commands, or error texts. Never infers invocation from tool failures and never
creates/edits/deletes skills, logs, baselines, or approval records.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = 1
MAX_RUNS = 500
MAX_BYTES = 1024 * 1024
IDENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
HOSTS = {"codex", "claude", "cursor", "gemini", "opencode", "other"}
PHASES = {"baseline", "candidate"}
EXPECTED = {"invoke", "skip"}
OBSERVED = {"invoke", "skip", "unknown"}
VERIFICATION = {"pass", "fail", "unknown"}
EVIDENCE = {"host_trace", "reviewed_manual", "none"}
FIELDS = {"case_id", "phase", "skill", "host", "expected", "observed",
          "verification", "evidence", "skill_tokens"}


class EffectivenessError(ValueError):
    """Unsafe, malformed, or incomparable measurement input."""


def _slug(value: object, field: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise EffectivenessError(f"{field} must be a short de-identified slug")
    return value


def _enum(value: object, choices: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise EffectivenessError(f"Invalid {field}")
    return value


def validate(data: object) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or set(data) != {"schema_version", "suite_id", "runs"} or data["schema_version"] != SCHEMA:
        raise EffectivenessError("Expected schema_version=1, suite_id, runs only")
    _slug(data["suite_id"], "suite_id")
    raw_runs = data["runs"]
    if not isinstance(raw_runs, list) or len(raw_runs) > MAX_RUNS:
        raise EffectivenessError("runs must be a list of at most 500 entries")
    entries = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in raw_runs:
        if not isinstance(raw, dict) or set(raw) != FIELDS:
            raise EffectivenessError("Each run needs exactly the documented privacy-safe fields")
        entry = {
            "case_id": _slug(raw["case_id"], "case_id"),
            "phase": _enum(raw["phase"], PHASES, "phase"),
            "skill": _slug(raw["skill"], "skill"),
            "host": _enum(raw["host"], HOSTS, "host"),
            "expected": _enum(raw["expected"], EXPECTED, "expected"),
            "observed": _enum(raw["observed"], OBSERVED, "observed"),
            "verification": _enum(raw["verification"], VERIFICATION, "verification"),
            "evidence": _enum(raw["evidence"], EVIDENCE, "evidence"),
            "skill_tokens": raw["skill_tokens"],
        }
        key = (entry["phase"], entry["host"], entry["skill"], entry["case_id"])
        if key in seen:
            raise EffectivenessError("Duplicate phase/host/skill/case_id record")
        seen.add(key)
        if (entry["observed"] == "unknown") != (entry["evidence"] == "none"):
            raise EffectivenessError("Observed invocation requires host_trace or reviewed_manual; unknown requires none")
        if entry["verification"] != "unknown" and not (
            entry["observed"] == "invoke" and entry["expected"] == "invoke"
        ):
            raise EffectivenessError("Verification is only defined for expected and observed invocations")
        tokens = entry["skill_tokens"]
        if tokens is not None and (
            type(tokens) is not int or tokens < 0 or tokens > 1_000_000_000
            or entry["evidence"] != "host_trace" or entry["observed"] != "invoke"
        ):
            raise EffectivenessError("skill_tokens requires a measured host_trace invocation (nonnegative integer)")
        entries.append(entry)
    return entries


def _ratio(a: int, b: int) -> dict[str, Any]:
    return {"numerator": a, "denominator": b, "value": a / b if b else None}


def _metrics(group: list[dict[str, Any]], phase: str, host: str, skill: str) -> dict[str, Any]:
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    unknown = 0
    passed = failed = unverifiable = 0
    measured = []
    for x in group:
        if x["observed"] == "unknown":
            unknown += 1
        else:
            lookup = {("invoke", "invoke"): "tp", ("invoke", "skip"): "fn",
                      ("skip", "invoke"): "fp", ("skip", "skip"): "tn"}
            counts[lookup[x["expected"], x["observed"]]] += 1
        if x["expected"] == "invoke" and x["observed"] == "invoke":
            if x["verification"] == "pass":
                passed += 1
            elif x["verification"] == "fail":
                failed += 1
            else:
                unverifiable += 1
        if x["skill_tokens"] is not None:
            measured.append(x["skill_tokens"])
    tokens = {"measured_cases": len(measured),
              "min": min(measured) if measured else None,
              "max": max(measured) if measured else None,
              "mean": sum(measured) / len(measured) if measured else None}
    return {"phase": phase, "host": host, "skill": skill, "cases": len(group),
            "unobserved": unknown, "confusion": counts,
            "activation_precision": _ratio(counts["tp"], counts["tp"] + counts["fp"]),
            "activation_recall": _ratio(counts["tp"], counts["tp"] + counts["fn"]),
            "verification_success": _ratio(passed, passed + failed),
            "verification_unknown": unverifiable,
            "skill_tokens": tokens}


def evaluate(data: object) -> dict[str, Any]:
    runs = validate(data)
    by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    by_case: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for x in runs:
        by_group[x["phase"], x["host"], x["skill"]].append(x)
        by_case[x["host"], x["skill"], x["case_id"]][x["phase"]] = x
    metrics = [_metrics(by_group[k], *k) for k in sorted(by_group)]
    matched = 0
    determined = 0
    verification_compared = 0
    activation_regressions: list[str] = []
    verification_regressions: list[str] = []
    unknown_pairs = 0
    for (host, skill, case_id), phases in sorted(by_case.items()):
        if "baseline" not in phases or "candidate" not in phases:
            continue
        matched += 1
        before, after = phases["baseline"], phases["candidate"]
        if before["expected"] != after["expected"]:
            raise EffectivenessError("Paired scenarios have conflicting expected invocation labels")
        if before["observed"] == "unknown" or after["observed"] == "unknown":
            unknown_pairs += 1
            continue
        determined += 1
        old_match = before["observed"] == before["expected"]
        new_match = after["observed"] == after["expected"]
        if old_match and not new_match:
            activation_regressions.append(f"{host}/{skill}/{case_id}")
        if before["verification"] != "unknown" and after["verification"] != "unknown":
            verification_compared += 1
            if before["verification"] == "pass" and after["verification"] == "fail":
                verification_regressions.append(f"{host}/{skill}/{case_id}")
    # Explicit, reviewed failure evidence merits an investigation even without a baseline.
    candidate_failures = [x for x in runs if x["phase"] == "candidate" and (
        (x["observed"] != "unknown" and x["observed"] != x["expected"])
        or x["verification"] == "fail")]
    candidate = [x for x in runs if x["phase"] == "candidate"]
    candidate_unmatched = any("baseline" not in by_case[x["host"], x["skill"], x["case_id"]]
                              for x in candidate)
    candidate_labels = {x["expected"] for x in candidate}
    if activation_regressions or verification_regressions or candidate_failures:
        status, action = "review_recommended", "review_existing"
    elif (not matched or determined < matched or candidate_unmatched or
          not {"invoke", "skip"}.issubset(candidate_labels)):
        status, action = "insufficient_evidence", "collect_evidence"
    elif any(x["phase"] == "candidate" and x["expected"] == "invoke" and
             x["observed"] == "invoke" and x["verification"] == "unknown" for x in runs):
        status, action = "insufficient_evidence", "collect_evidence"
    else:
        status, action = "no_change", "no_change"
    return {
        "schema_version": SCHEMA, "suite_id": data["suite_id"],
        "status": status, "action": action,
        "metrics": metrics,
        "comparison": {
            "matched_pairs": matched, "determined_pairs": determined,
            "unknown_pairs": unknown_pairs,
            "verification_compared": verification_compared,
            "activation_regressions": activation_regressions,
            "verification_regressions": verification_regressions,
        },
        "limitations": [
            "Labels/evidence were supplied by reviewers or the host; this evaluator cannot authenticate them.",
            "Counts and rates describe the supplied cases, not all real agent invocations.",
            "skill_tokens are host-measured, optional, and not comparable across differing hosts or harnesses.",
            "No automated skill creation, edits, retirement, or quality claims from missing data.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only, bounded Skill effectiveness scenario evaluator")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("evaluate", help="Assess a reviewed scenario suite without changing project files")
    run.add_argument("--suite", type=Path, required=True)
    args = parser.parse_args()
    try:
        p = args.suite
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            raise EffectivenessError("Suite must be a regular, bounded JSON file")
        doc = json.loads(p.read_text(encoding="utf-8"))
        print(json.dumps(evaluate(doc), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (EffectivenessError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Evaluation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
