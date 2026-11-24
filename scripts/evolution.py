#!/usr/bin/env python3
"""Read-only, deterministic triage of project skill-architecture evolution.

This does NOT understand source semantics or generate skills. It evaluates typed
human/agent observations and optionally a checkpoint diff, then recommends at
most one *review* of an existing workflow. It makes no repository changes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

# Locate the bundled detector even when tests load this module by file path.
_CHECKPOINT_SPEC = importlib.util.spec_from_file_location("skill_architect_checkpoint", Path(__file__).with_name("checkpoint.py"))
_checkpoint = importlib.util.module_from_spec(_CHECKPOINT_SPEC)
_CHECKPOINT_SPEC.loader.exec_module(_checkpoint)

SCHEMA = 1
MAX_JSON_BYTES = 128 * 1024
MAX_OBSERVATIONS = 100
MAX_DECISIONS = 100
MAX_PATHS = 8
VALID_KINDS = {
    "new-service", "architecture-change", "workflow-change",
    "agent-failure", "skill-gap", "host-change",
}
VALID_SOURCES = {"user", "agent", "ci", "review", "repo"}
REVIEWABLE_CHECKPOINT = {"instruction", "skill", "agent-integration"}
KNOWN_CHECKPOINT = REVIEWABLE_CHECKPOINT | {"ci", "project-configuration", "explicit-checkpoint"}
TOPIC = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]{0,62}[a-z0-9])?$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")


class EvolutionError(ValueError):
    """Unsupported, unsafe, or ambiguous evolution evidence."""


def _object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvolutionError(message)
    return value


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 300 or "\x00" in value:
        raise EvolutionError("Evidence paths must be nonempty bounded relative paths")
    if "\\" in value or value.startswith("/") or ":" in value:
        raise EvolutionError("Evidence paths must be normalized repository-relative POSIX paths")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"..", "."} for part in value.split("/")) or "//" in value:
        raise EvolutionError("Evidence paths cannot traverse or normalize directories")
    if any(part == ".git" or part.startswith(".env") for part in parts):
        raise EvolutionError("Do not collect secret or Git-private paths as observations")
    return value


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise EvolutionError(f"Invalid {label}; use a short stable identifier")
    return value


def validate_observations(data: object) -> list[dict[str, Any]]:
    obj = _object(data, "Observations must be a JSON object")
    if set(obj) != {"schema_version", "observations"} or obj["schema_version"] != SCHEMA:
        raise EvolutionError("Invalid observations schema; expected schema_version 1 and observations")
    entries = obj["observations"]
    if not isinstance(entries, list) or len(entries) > MAX_OBSERVATIONS:
        raise EvolutionError("Observations must be a bounded list (max 100)")
    ids: set[str] = set()
    clean: list[dict[str, Any]] = []
    for raw in entries:
        row = _object(raw, "Every observation must be a JSON object")
        if not {"id", "kind", "topic", "source", "summary", "evidence_paths"}.issubset(row) or (
            set(row) - {"id", "kind", "topic", "source", "summary", "evidence_paths", "occurrence"}
        ):
            raise EvolutionError("Observation requires id, kind, topic, source, summary, evidence_paths; optional occurrence")
        key = _id(row["id"], "observation id")
        if key in ids:
            raise EvolutionError(f"Duplicate observation ID: {key}")
        ids.add(key)
        if not isinstance(row["kind"], str) or row["kind"] not in VALID_KINDS:
            raise EvolutionError(f"Unknown observation kind: {str(row['kind'])[:60]}")
        if not isinstance(row["topic"], str) or not TOPIC.fullmatch(row["topic"]):
            raise EvolutionError("Topic must be a stable lowercase slug")
        if not isinstance(row["source"], str) or row["source"] not in VALID_SOURCES:
            raise EvolutionError("Unknown observation source")
        if not isinstance(row["summary"], str) or not 1 <= len(row["summary"]) <= 400:
            raise EvolutionError("Observation summary must be 1..400 characters")
        paths = row["evidence_paths"]
        if not isinstance(paths, list) or len(paths) > MAX_PATHS:
            raise EvolutionError("evidence_paths must be a list of at most eight paths")
        if len(paths) != len(set(_path(p) for p in paths)):
            raise EvolutionError("Duplicate evidence path")
        occurrence = row.get("occurrence")
        if row["kind"] == "agent-failure":
            occurrence = _id(occurrence, "failure occurrence")
        elif occurrence is not None:
            occurrence = _id(occurrence, "occurrence")
        clean.append({"id": key, "kind": row["kind"], "topic": row["topic"],
                      "source": row["source"], "summary": row["summary"],
                      "evidence_paths": paths, "occurrence": occurrence})
    return clean


def validate_decisions(data: object | None) -> dict[str, tuple[str, set[str]]]:
    if data is None:
        return {}
    obj = _object(data, "Decision history must be a JSON object")
    if set(obj) != {"schema_version", "decisions"} or obj["schema_version"] != SCHEMA:
        raise EvolutionError("Invalid decisions schema")
    entries = obj["decisions"]
    if not isinstance(entries, list) or len(entries) > MAX_DECISIONS:
        raise EvolutionError("Decisions must be a bounded list (max 100)")
    result = {}
    for raw in entries:
        row = _object(raw, "Every decision must be an object")
        if set(row) != {"candidate_key", "decision", "evidence_ids"}:
            raise EvolutionError("Decision fields must be candidate_key, decision, evidence_ids")
        key = row["candidate_key"]
        if not isinstance(key, str) or len(key) > 130 or not re.fullmatch(r"[a-z-]+:[a-z0-9-]+", key):
            raise EvolutionError("Invalid candidate_key")
        if key in result:
            raise EvolutionError("Multiple decisions for same candidate; supply current decision only")
        decision = row["decision"]
        if not isinstance(decision, str) or decision not in {"declined", "accepted", "resolved"}:
            raise EvolutionError("Invalid decision disposition")
        ids = row["evidence_ids"]
        if not isinstance(ids, list) or len(ids) > 100 or not ids:
            raise EvolutionError("Decision needs the evidence IDs from a reviewed recommendation")
        if any(not isinstance(x, str) or not 1 <= len(x) <= 500 for x in ids):
            raise EvolutionError("Invalid decision evidence identifier")
        result[key] = (decision, set(ids))
    return result


def _present(repo: Path, rel: str) -> bool:
    """Presence only; no file content is read and symlinks are never evidence."""
    try:
        current = repo.resolve()
        for part in PurePosixPath(rel).parts:
            current = current / part
            if current.is_symlink():
                return False
        return current.exists() and current.resolve().is_relative_to(repo.resolve())
    except (OSError, ValueError):
        return False


def _checkpoint_signals(checkpoint: object | None) -> tuple[list[dict[str, Any]], bool]:
    if checkpoint is None:
        return [], False
    obj = _object(checkpoint, "Checkpoint report must be an object")
    status = obj.get("status")
    if not isinstance(status, str) or status not in {"review_suggested", "no_relevant_change", "insufficient_evidence"}:
        raise EvolutionError("Unsupported checkpoint report status")
    signals = obj.get("signals", [])
    if not isinstance(signals, list) or len(signals) > 50:
        raise EvolutionError("Invalid checkpoint signals")
    clean = []
    for signal in signals:
        s = _object(signal, "Invalid checkpoint signal")
        kind = s.get("kind")
        if not isinstance(kind, str) or kind not in KNOWN_CHECKPOINT:
            raise EvolutionError("Unknown checkpoint kind")
        paths = s.get("paths", [])
        if not isinstance(paths, list) or len(paths) > 100:
            raise EvolutionError("Invalid checkpoint paths")
        clean.append({"kind": kind, "paths": [_path(p) for p in paths]})
    if status == "no_relevant_change" and signals:
        raise EvolutionError("Inconsistent checkpoint: no change with signals")
    return clean, status != "insufficient_evidence"


def _proposal(priority: int, key: str, ids: list[str], strength: str, rationale: str) -> dict[str, Any]:
    return {"priority": priority, "candidate_key": key, "decision": "review_existing",
            "evidence_ids": sorted(set(ids)), "evidence_strength": strength, "rationale": rationale,
            "review_instruction": "Inspect current approved instructions and skills; verify the workflow gap. "
                                  "Prefer no change or revising an existing artifact. Propose a new skill "
                                  "only if distinct, repeatable, triggerable, and testable. Request approval before edits."}


def assess(repo: Path, observations: object, *, checkpoint: object | None = None,
           decisions: object | None = None) -> dict[str, Any]:
    """Purely advisory evaluation; caller must provide evidence, no repo writes."""
    repo = repo.resolve()
    if not repo.is_dir():
        raise EvolutionError("Repository directory does not exist")
    rows = validate_observations(observations)
    decisions_by_key = validate_decisions(decisions)
    signals, comparable = _checkpoint_signals(checkpoint)
    proposals: list[dict[str, Any]] = []

    # Count distinct, reported occurrences for one stable failure topic.
    failures: dict[str, list[dict[str, Any]]] = {}
    for obs in rows:
        if obs["kind"] == "agent-failure":
            failures.setdefault(obs["topic"], []).append(obs)
    for topic, group in sorted(failures.items()):
        occurrences = {item["occurrence"] for item in group}
        if len(occurrences) >= 2:
            proposals.append(_proposal(10, f"agent-failure:{topic}", [x["id"] for x in group],
                                       "repeated-reported-not-independently-verified",
                                       "At least two separately identified occurrences of the same reported failure; inspect the existing workflow first."))

    # A semantic label is always reported, never inferred from a filename.
    # Group equivalent reports so repeated notes cannot spam the candidate queue.
    change_groups: dict[tuple[str, str], list[str]] = {}
    for obs in rows:
        if obs["kind"] == "agent-failure":
            continue
        if obs["source"] != "user" or not any(_present(repo, p) for p in obs["evidence_paths"]):
            continue
        change_groups.setdefault((obs["kind"], obs["topic"]), []).append(obs["id"])
    for (kind, topic), ids in sorted(change_groups.items()):
        priority = 20 if kind == "skill-gap" else 30
        proposals.append(_proposal(priority, f"{kind}:{topic}", ids,
                                   "user-reported-path-present",
                                   "A user-reported change has a matching repository path; its semantic significance remains unverified."))

    # Checkpoints show *changes*, never independently establish incompatibility.
    allowed_paths = {}
    for signal in signals:
        if signal["kind"] in REVIEWABLE_CHECKPOINT and signal["paths"]:
            allowed_paths.setdefault(signal["kind"], set()).update(signal["paths"])
    states = _checkpoint.snapshot(repo)["files"] if allowed_paths else {}
    for kind, paths in sorted(allowed_paths.items()):
        evidence = []
        for path in sorted(paths):
            # Bind suppression to current material, not just the persistent path name.
            # checkpoint.snapshot only hashes allowlisted, size-bounded files.
            digest = states.get(path, "absent-or-unscanned")
            evidence.append(f"checkpoint:{kind}:{path}:{digest}")
        proposals.append(_proposal(40, f"checkpoint:{kind}", evidence,
                                   "file-change-candidate-not-proof",
                                   "Instruction, skill, or host configuration changed; reconcile the current contract."))

    active = []
    suppressed = 0
    for proposal in proposals:
        previous = decisions_by_key.get(proposal["candidate_key"])
        if previous and set(proposal["evidence_ids"]).issubset(previous[1]):
            suppressed += 1
        else:
            active.append(proposal)
    active.sort(key=lambda p: (p["priority"], p["candidate_key"]))
    recommendation = active[0] if active else None
    if recommendation:
        status = "review_recommended"
    elif proposals and suppressed == len(proposals):
        status = "no_change"
    elif rows or signals:
        status = "watch"
    elif comparable:
        status = "no_change"
    else:
        status = "insufficient_evidence"

    # No raw observation summaries are emitted as operational instructions.
    if recommendation:
        recommendation = {key: value for key, value in recommendation.items() if key != "priority"}
    return {
        "schema_version": SCHEMA,
        "status": status,
        "recommendation": recommendation,
        "deferred_candidates": max(0, len(active) - 1),
        "suppressed_candidates": suppressed,
        "observations_received": len(rows),
        "checkpoint_signals_received": len(signals),
        "limits": "Observations are reports, not verified source semantics. File presence does not verify a claim; "
                  "repeated occurrences are reported, not independently verified. This tool makes no edits, "
                  "runs no LLM, and cannot ensure automatic skill invocation.",
    }


def _load_json(path: Path) -> object:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON_BYTES:
            raise EvolutionError("Input JSON is a symlink or exceeds 128 KiB limit")
        raw = path.read_bytes()
        if len(raw) > MAX_JSON_BYTES:
            raise EvolutionError("Input JSON exceeds 128 KiB limit")
        return json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvolutionError(f"Cannot read JSON input: {type(exc).__name__}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--observations", type=Path, help="Typed observations JSON (read-only)")
    parser.add_argument("--decisions", type=Path, help="Previously reviewed candidate IDs (read-only)")
    parser.add_argument("--event", default="manual")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--since-ref", help="Compared Git base revision")
    group.add_argument("--baseline", type=Path, help="Approved snapshot baseline")
    args = parser.parse_args(argv)
    try:
        checkpoint = _checkpoint.evaluate(args.repo, event=args.event, since_ref=args.since_ref,
                              baseline=args.baseline) if (args.baseline or args.since_ref or args.event != "manual") else None
        observations = _load_json(args.observations) if args.observations else {"schema_version": SCHEMA, "observations": []}
        decisions = _load_json(args.decisions) if args.decisions else None
        result = assess(args.repo, observations, checkpoint=checkpoint, decisions=decisions)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (EvolutionError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
