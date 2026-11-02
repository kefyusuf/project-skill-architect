#!/usr/bin/env python3
"""Opt-in, privacy-minimizing tool-failure intake and reviewed evolution handoff.

Only opted-in host hooks call ingest; it stores categorical, salted metadata in
Git-private state. No prompts, transcript, command, tool arguments, or errors
are persisted. Review/evaluate never edit skill files or approval history.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = 1
MAX_STDIN = 64 * 1024
MAX_LEDGER = 128 * 1024
MAX_EVENTS = 200
SAFE_TOPIC = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]{0,62}[a-z0-9])?$")


class EventError(ValueError):
    pass


def _require_token(value: Any) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 200):
        raise EventError("Missing or invalid opaque event identity")
    return value


def _git_dir(repo: Path) -> Path:
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise EventError("Repository not found")
    try:
        root = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=3, check=True).stdout.strip()
        git = subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
                             capture_output=True, text=True, timeout=3, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise EventError("A local Git repository is required") from exc
    if Path(root).resolve() != repo:
        raise EventError("--repo must be the repository root")
    path = Path(git)
    if not path.is_absolute() or not path.is_dir():
        raise EventError("Could not locate local Git-private storage")
    return path


def _state_path(repo: Path) -> Path:
    directory = _git_dir(repo) / "project-skill-architect"
    if directory.is_symlink():
        raise EventError("Git-private state directory must not be a symlink")
    path = directory / "events.json"
    if path.is_symlink():
        raise EventError("Refusing to read a symlinked ledger")
    return path


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LEDGER:
        raise EventError("Unsafe or oversized event ledger")
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise EventError("Unreadable event ledger") from exc
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "salt", "events"} or ledger["schema_version"] != SCHEMA:
        raise EventError("Invalid event ledger schema")
    if not isinstance(ledger["salt"], str) or not re.fullmatch(r"[a-f0-9]{32}", ledger["salt"]):
        raise EventError("Invalid state salt")
    entries = ledger["events"]
    if not isinstance(entries, list) or len(entries) > MAX_EVENTS:
        raise EventError("Invalid bounded event collection")
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"id", "session", "host", "category", "captured_at"}:
            raise EventError("Unexpected event fields")
        if (not all(isinstance(v, str) for v in item.values())
            or item["host"] not in {"codex", "claude"}
            or item["category"] not in {"shell", "edit", "read", "search", "other"}
            or not re.fullmatch(r"[a-f0-9]{24}", item["id"])
            or not re.fullmatch(r"[a-f0-9]{24}", item["session"])
            or len(item["captured_at"]) > 32):
            raise EventError("Invalid event entry")
    return ledger


def _save(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = (json.dumps(ledger, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_LEDGER:
        raise EventError("Event ledger size exceeded")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".events-", suffix=".tmp", dir=path.parent,
                                         delete=False) as f:
            temp = Path(f.name)
            os.chmod(temp, 0o600)
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        if path.is_symlink():
            raise EventError("Refusing to replace symlinked event ledger")
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _category(name: Any) -> str:
    if not isinstance(name, str) or len(name) > 160:
        return "other"
    if name in {"Bash", "exec_command", "functions.command"}:
        return "shell"
    if name in {"Write", "Edit", "apply_patch", "MultiEdit"}:
        return "edit"
    if name in {"Read"}:
        return "read"
    if name in {"Glob", "Grep"}:
        return "search"
    return "other"


def _accept_event(host: str, event: dict[str, Any], repo: Path) -> tuple[str, str, str] | None:
    """No raw text is returned; only opaque identifiers and a coarse category."""
    if event.get("cwd") is None or not isinstance(event["cwd"], str):
        return None
    try:
        cwd = Path(event["cwd"]).resolve()
        if not cwd.is_relative_to(repo.resolve()):
            return None
    except (OSError, ValueError):
        return None
    if host == "claude":
        if event.get("hook_event_name") != "PostToolUseFailure" or event.get("is_interrupt") is True:
            return None
    elif host == "codex":
        if event.get("hook_event_name") != "PostToolUse":
            return None
        # The response may be arbitrary text, a dict, or plugin-dependent. Only
        # an explicit structured nonzero shell exit is a verified failure.
        if event.get("tool_name") != "Bash":
            return None
        response = event.get("tool_response")
        if not isinstance(response, dict):
            return None
        code = response.get("exit_code")
        if not isinstance(code, int) or isinstance(code, bool) or code == 0:
            return None
    else:
        raise EventError("Unknown host")
    session = _require_token(event.get("session_id"))
    invocation = _require_token(event.get("tool_use_id"))
    return session, invocation, _category(event.get("tool_name"))


def _digest(salt: str, *parts: str) -> str:
    data = "\x00".join((salt, *parts)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:24]


def ingest(repo: Path, host: str, event: object) -> dict[str, object]:
    repo = repo.expanduser().resolve()
    # Ignore irrelevant host events without creating local state.
    if not isinstance(event, dict):
        return {"status": "ignored"}
    extracted = _accept_event(host, event, repo)
    if extracted is None:
        return {"status": "ignored"}
    path = _state_path(repo)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise EventError("Unsafe state directory")
    # Nonblocking exclusive lock; concurrent events may be skipped, never
    # counted twice. No side effects in the repository working tree.
    lock = path.with_name("events.lock")
    if lock.is_symlink():
        raise EventError("Unsafe event lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {"status": "busy", "note": "Best-effort intake; the event was not saved"}
    try:
        os.close(fd)
        ledger = _read(path)
        if ledger is None:
            ledger = {"schema_version": SCHEMA, "salt": secrets.token_hex(16), "events": []}
        session, call, category = extracted
        event_id = _digest(ledger["salt"], host, session, call)
        if any(item["id"] == event_id for item in ledger["events"]):
            return {"status": "duplicate", "event_id": event_id}
        entry = {"id": event_id, "session": _digest(ledger["salt"], host, session),
                 "host": host, "category": category,
                 "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        ledger["events"].append(entry)
        ledger["events"] = ledger["events"][-MAX_EVENTS:]
        _save(path, ledger)
        return {"status": "recorded", "event_id": event_id}
    finally:
        lock.unlink(missing_ok=True)


def inspect(repo: Path) -> dict[str, object]:
    ledger = _read(_state_path(repo))
    entries = ledger["events"] if ledger else []
    return {"schema_version": SCHEMA, "events": len(entries),
            "distinct_sessions": len({e["session"] for e in entries}),
            "by_host": dict(sorted(Counter(e["host"] for e in entries).items())),
            "by_category": dict(sorted(Counter(e["category"] for e in entries).items())),
            "recent_events": [dict(e) for e in entries[-20:]],
            "limits": "Metadata only; these are tool failures, not proven skill gaps."}


def evaluate(repo: Path, topic: str, selected: list[str], decisions: object | None = None) -> dict[str, Any]:
    if not SAFE_TOPIC.fullmatch(topic):
        raise EventError("Topic must be a stable lowercase workflow slug")
    if len(selected) < 2 or len(selected) > 12 or len(selected) != len(set(selected)):
        raise EventError("Select 2..12 distinct event IDs after reviewing the same workflow")
    ledger = _read(_state_path(repo))
    if ledger is None:
        raise EventError("No collected events exist")
    by_id = {e["id"]: e for e in ledger["events"]}
    if any(event_id not in by_id for event_id in selected):
        raise EventError("Unknown or expired event ID")
    rows = [by_id[event_id] for event_id in selected]
    if len({e["session"] for e in rows}) < 2:
        raise EventError("Two independent sessions required to avoid counting retries")
    if len({e["category"] for e in rows}) != 1:
        raise EventError("Mixed tool categories require separate workflow reviews")
    observations = {"schema_version": 1, "observations": [
        {"id": e["id"], "kind": "agent-failure", "topic": topic, "source": "agent",
         "summary": "Selected tool-failure metadata; matching workflow is user-reviewed, not mechanically established",
         "evidence_paths": [], "occurrence": e["session"]}
        for e in rows
    ]}
    spec = importlib.util.spec_from_file_location("skill_architect_evolution", Path(__file__).with_name("evolution.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.assess(repo, observations, decisions=decisions)
    result["v6_provenance"] = "User-curated event IDs; no raw tool output retained; workflow equality not verified by the tool."
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    p_ingest = subs.add_parser("ingest", help="Opt-in host hook: stores redacted metadata in Git-private state")
    p_ingest.add_argument("--host", required=True, choices=("codex", "claude"))
    p_inspect = subs.add_parser("inspect", help="Summarize local failure events, read-only")
    p_eval = subs.add_parser("evaluate", help="Explicitly curate two or more independent failure events")
    p_eval.add_argument("--topic", required=True)
    p_eval.add_argument("--event-ids", nargs="+", required=True)
    p_eval.add_argument("--decisions", type=Path)
    for p in (p_ingest, p_inspect, p_eval):
        p.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            raw = sys.stdin.buffer.read(MAX_STDIN + 1)
            if len(raw) > MAX_STDIN:
                raise EventError("Hook event exceeds maximum input size")
            event = json.loads(raw) if raw else {}
            output = ingest(args.repo, args.host, event)
            # Hook output is silent: don't contaminate agent context or logs.
            return 0 if output["status"] in {"recorded", "duplicate", "ignored", "busy"} else 1
        elif args.command == "inspect":
            output = inspect(args.repo)
        else:
            decisions = None
            if args.decisions:
                source = args.decisions
                if source.is_symlink() or source.stat().st_size > MAX_LEDGER:
                    raise EventError("Unsafe decision file")
                decisions = json.loads(source.read_text(encoding="utf-8"))
            output = evaluate(args.repo, args.topic, args.event_ids, decisions)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (EventError, OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        if args.command == "ingest":
            return 0  # Advisory hook must never disrupt the coding task.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
