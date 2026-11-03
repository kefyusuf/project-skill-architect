#!/usr/bin/env python3
"""Read-only checkpoint detection for a project's skill architecture.

Evidence sources are an explicit Git comparison or an explicitly saved snapshot.
This script never changes project files or creates, edits, or activates skills.
A baseline is written only by the --save-baseline command-line option.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
INSTRUCTIONS = {
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
}
INTEGRATIONS = {".codex/hooks.json", ".claude/settings.json", ".claude/settings.local.json"}
MANIFESTS = {
    "composer.json", "package.json", "pyproject.toml", "requirements.txt",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Makefile",
}
CI = {".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"}
SKILL_ROOTS = (
    ".agents/skills/", ".claude/skills/", ".cursor/skills/",
    ".gemini/skills/", ".opencode/skills/", ".github/skills/",
)
SKILL_SUBDIRS = {"scripts", "references", "assets"}
SKILL_EXTENSIONS = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml"}
SKIP_PARTS = {"__pycache__", "node_modules", ".git", ".venv", ".pytest_cache"}
MAX_FILES = 500
MAX_BYTES = 128 * 1024
MAX_DIFF_BYTES = 2 * 1024 * 1024
EVENTS = ("manual", "pr", "release", "architecture", "workflow", "agent-change", "repeated-failure")
EXPLICIT_EVENTS = {"architecture", "workflow", "agent-change", "repeated-failure"}
REF = re.compile(r"^[A-Za-z0-9_./^~{}+-]+$")


class CheckpointError(ValueError):
    pass


def classify(path: str) -> str | None:
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p in INSTRUCTIONS:
        return "instruction"
    if p in INTEGRATIONS:
        return "agent-integration"
    if p in CI or (p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))):
        return "ci"
    if p in MANIFESTS:
        return "project-configuration"
    for root in SKILL_ROOTS:
        if p.startswith(root):
            rel = p[len(root):].split("/")
            if len(rel) >= 2 and rel[1] == "SKILL.md":
                return "skill"
            if len(rel) >= 3 and rel[1] in SKILL_SUBDIRS and Path(rel[-1]).suffix in SKILL_EXTENSIONS:
                return "skill"
    return None


def _within_repo(repo: Path, file: Path) -> bool:
    try:
        return file.resolve().is_relative_to(repo.resolve())
    except (OSError, ValueError):
        return False


def snapshot(repo: Path) -> dict[str, object]:
    """Fingerprint a bounded allowlist of workflow-related files; no app code/secrets."""
    if not repo.is_dir():
        raise CheckpointError(f"Repository directory not found: {repo}")
    repo = repo.resolve()
    candidates: set[Path] = {repo / path for path in INSTRUCTIONS | MANIFESTS | CI | INTEGRATIONS}
    for root_name in SKILL_ROOTS:
        root = repo / root_name
        if root.is_symlink() or not root.is_dir():
            continue
        # Only immediate skill directories and their known resources are supported.
        for skill in root.iterdir():
            if not skill.is_dir() or skill.is_symlink():
                continue
            candidates.add(skill / "SKILL.md")
            for sub in SKILL_SUBDIRS:
                folder = skill / sub
                if not folder.is_dir() or folder.is_symlink():
                    continue
                for current_dir, subdirs, filenames in os.walk(folder, followlinks=False):
                    current = Path(current_dir)
                    subdirs[:] = sorted(d for d in subdirs if d not in SKIP_PARTS and not (current / d).is_symlink())
                    for name in filenames:
                        if Path(name).suffix in SKILL_EXTENSIONS and name not in SKIP_PARTS:
                            candidates.add(current / name)
    workflow_root = repo / ".github/workflows"
    if workflow_root.is_dir() and not workflow_root.is_symlink():
        candidates.update(p for p in workflow_root.iterdir() if p.suffix in {".yml", ".yaml"})
    result: dict[str, str] = {}
    skipped: list[str] = []
    limit = False
    for path in sorted(candidates, key=lambda p: p.as_posix()):
        if not path.is_file() or path.is_symlink() or not _within_repo(repo, path):
            continue
        rel = path.relative_to(repo).as_posix()
        if classify(rel) is None:
            continue
        if len(result) >= MAX_FILES:
            limit = True
            break
        try:
            if path.stat().st_size > MAX_BYTES:
                skipped.append(rel)
                continue
            result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            skipped.append(rel)
    return {"schema_version": SCHEMA, "files": result, "incomplete": limit or bool(skipped),
            "skipped": skipped[:20], "limit_reached": limit}


def git_paths(repo: Path, ref: str) -> set[str]:
    if not REF.fullmatch(ref) or ref.startswith("-"):
        raise CheckpointError("Invalid base revision")
    try:
        base = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
                              capture_output=True, timeout=5, check=False)
        if base.returncode != 0:
            raise CheckpointError(f"Cannot verify base revision: {ref}")
        base_commit = base.stdout.decode("ascii", errors="replace").strip()
        result = subprocess.run(["git", "-C", str(repo), "-c", "core.fsmonitor=false",
                                 "diff", "--no-ext-diff", "--name-only", "-z", f"{base_commit}...HEAD", "--"],
                                capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            raise CheckpointError("Could not compare Git revisions (missing merge base or invalid repository)")
        if len(result.stdout) > MAX_DIFF_BYTES:
            raise CheckpointError("Git diff exceeds bounded checkpoint scan limit")
        return {p.decode("utf-8", errors="replace") for p in result.stdout.split(b"\0") if p}
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CheckpointError(f"Git comparison unavailable: {type(exc).__name__}") from exc


def read_baseline(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"Cannot read baseline: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise CheckpointError("Baseline schema version is not supported")
    files = data.get("files")
    if not isinstance(files, dict) or len(files) > MAX_FILES or any(
        not isinstance(k, str) or classify(k) is None or
        not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v)
        for k, v in files.items()
    ):
        raise CheckpointError("Baseline file hashes are invalid")
    if data.get("incomplete"):
        raise CheckpointError("Incomplete baseline cannot establish a clean comparison")
    return data


def evaluate(repo: Path, *, event: str = "manual", since_ref: str | None = None,
             baseline: Path | None = None) -> dict[str, object]:
    if event not in EVENTS:
        raise CheckpointError(f"Unknown event: {event}")
    if since_ref and baseline:
        raise CheckpointError("Provide either --since-ref or --baseline, not both")
    if since_ref:
        paths = git_paths(repo, since_ref)
        method = "git-comparison"
        complete = True
    elif baseline:
        old = read_baseline(baseline)
        new = snapshot(repo)
        old_files, new_files = old["files"], new["files"]
        paths = {p for p in set(old_files) | set(new_files) if old_files.get(p) != new_files.get(p)}
        method = "snapshot-comparison"
        complete = not new["incomplete"]
    else:
        paths = set()
        method = "no-comparison"
        complete = False

    by_type: dict[str, list[str]] = {}
    for path in sorted(paths):
        category = classify(path)
        if category:
            by_type.setdefault(category, []).append(path)
    signals = [{"kind": kind, "paths": values, "strength": "candidate-not-proof"}
               for kind, values in sorted(by_type.items())]
    if event in EXPLICIT_EVENTS:
        signals.append({"kind": "explicit-checkpoint", "event": event,
                        "strength": "user-or-host-declared-not-independently-verified"})
    if signals:
        status = "review_suggested"
    elif not complete:
        status = "insufficient_evidence"
    else:
        status = "no_relevant_change"
    return {
        "schema_version": SCHEMA,
        "mode": "Evolve" if (since_ref or baseline) else "Adopt / explicit Evolve",
        "event": event, "comparison": method, "status": status,
        "signals": signals,
        "review_instruction": (
            "Invoke project-skill-architect in Evolve mode. Inspect approved project instructions "
            "and relevant evidence. Decide keep/revise/merge/add/retire/no-change; offer at most "
            "one justified improvement. Never modify files without authorization."
            if status == "review_suggested" else
            "Establish an approved baseline or provide a Git base revision before claiming there were no changes."
            if status == "insufficient_evidence" else
            "No relevant checkpoint signal. Continue the user's primary work without skill housekeeping."
        ),
        "limits": (
            "Only allowlisted root instructions, selected manifests/CI files and skill resources are compared. "
            "Changes are signals, not conclusions. Git comparison excludes uncommitted changes. "
            "No agent execution, monitoring, or file edits are performed."
        ),
    }


def save_baseline(path: Path, state: dict[str, object], *, replace: bool = False) -> None:
    if state["incomplete"]:
        raise CheckpointError("Refuse to save an incomplete baseline")
    if path.exists() and not replace:
        raise CheckpointError("Baseline already exists; use --replace-baseline after human review")
    if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
        raise CheckpointError("Refusing to write through a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    # No application content is stored; only allowlisted relative paths and hashes.
    data = json.dumps(state, indent=2, sort_keys=True) + "\n"
    if replace:
        path.write_text(data, encoding="utf-8")
    else:
        with path.open("x", encoding="utf-8") as output:
            output.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--event", choices=EVENTS, default="manual")
    comparison = parser.add_mutually_exclusive_group()
    comparison.add_argument("--since-ref", help="Compare committed changes from the Git merge-base with HEAD")
    comparison.add_argument("--baseline", type=Path, help="Compare working tree to a previously approved snapshot")
    parser.add_argument("--save-baseline", type=Path, help="Explicitly record a hash baseline, without reviewing")
    parser.add_argument("--replace-baseline", action="store_true", help="Acknowledge reviewed changes and replace baseline")
    args = parser.parse_args()
    try:
        repo = args.repo.expanduser().resolve()
        if args.replace_baseline and not args.save_baseline:
            raise CheckpointError("--replace-baseline requires --save-baseline")
        if args.save_baseline:
            if args.baseline or args.since_ref:
                raise CheckpointError("Saving a baseline is a separate operation from comparison")
            state = snapshot(repo)
            save_baseline(args.save_baseline.expanduser(), state, replace=args.replace_baseline)
            response = {"status": "baseline_saved", "path": str(args.save_baseline),
                        "tracked_files": len(state["files"]),
                        "note": "Only hashes stored. Explicit snapshot save does not approve any skill change."}
        else:
            response = evaluate(repo, event=args.event, since_ref=args.since_ref, baseline=args.baseline)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0
    except (CheckpointError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
