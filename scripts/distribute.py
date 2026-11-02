#!/usr/bin/env python3
"""Explicit, guarded cross-host installation of a canonical Agent Skill.

Default is a dry run. Copies are managed only after --apply, and existing
unmanaged or locally edited targets are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

MANIFEST = ".project-skill-architect-sync.json"
IDENTIFIER = "project-skill-architect-distributor-v1"
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", "tests"}
SKIP_FILES = {MANIFEST, ".DS_Store"}
TARGETS = {
    "common": ".agents/skills",  # Codex, Cursor, Gemini CLI, OpenCode
    "codex": ".agents/skills",
    "cursor": ".agents/skills",
    "gemini": ".agents/skills",
    "opencode": ".agents/skills",
    "claude": ".claude/skills",
    "copilot": ".github/skills",
}
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class DistributionError(Exception):
    pass


def source_files(directory: Path) -> dict[str, Path]:
    if not directory.is_dir() or directory.is_symlink() or not (directory / "SKILL.md").is_file():
        raise DistributionError(f"Source must be a real skill folder with SKILL.md: {directory}")
    if not NAME.fullmatch(directory.name):
        raise DistributionError(f"Invalid skill folder name: {directory.name}")
    files: dict[str, Path] = {}
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if any(part in SKIP_DIRS for part in relative.parts) or path.name in SKIP_FILES:
            continue
        if path.is_symlink():
            raise DistributionError(f"Source contains a symlink: {path}")
        if path.is_file():
            files[relative.as_posix()] = path
    return dict(sorted(files.items()))


def fingerprints(files: dict[str, Path]) -> dict[str, str]:
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def target_state(target: Path, desired: dict[str, str]) -> tuple[str, str]:
    if target.is_symlink():
        return ("BLOCK", "target is a symlink")
    if not target.exists():
        return ("CREATE", "new target")
    if not target.is_dir():
        return ("BLOCK", "target is not a directory")
    present_files = source_files(target) if (target / "SKILL.md").is_file() else {}
    present = fingerprints(present_files) if present_files else {}
    if not (target / MANIFEST).is_file():
        if present and present == desired:
            return ("UNCHANGED", "unmanaged identical copy; will not claim ownership")
        return ("BLOCK", "existing target is unmanaged; do not overwrite")
    try:
        info = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ("BLOCK", "unreadable ownership manifest")
    if info.get("managed_by") != IDENTIFIER or info.get("name") != target.name:
        return ("BLOCK", "ownership manifest does not match")
    if info.get("files") != present:
        return ("BLOCK", "managed copy changed since last sync; inspect before replacing")
    if desired == present:
        return ("UNCHANGED", "already synchronized")
    return ("UPDATE", "previously managed copy is unmodified")


def _staging_mode(platform: str) -> int:
    # Installed skills must be readable by the host's sandbox account.
    # Windows mkdtemp() forces a protected 0700 DACL; inherit the parent ACL
    # instead. Keep a private staging directory on POSIX.
    return 0o777 if platform == "win32" else 0o700


def install(source: Path, target: Path, files: dict[str, Path], desired: dict[str, str]) -> None:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = parent / f".{target.name}.stage-{uuid.uuid4().hex}"
    stage.mkdir(mode=_staging_mode(sys.platform))
    backup: Path | None = None
    try:
        for relative, path in files.items():
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        (stage / MANIFEST).write_text(json.dumps({
            "managed_by": IDENTIFIER,
            "name": source.name,
            "files": desired,
            "note": "Derived from a canonical skill; modify the source and re-run distribution.",
        }, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            backup = parent / f".{target.name}.backup-{uuid.uuid4().hex}"
            target.rename(backup)
        try:
            stage.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def plan(source: Path, repo: Path, targets: str) -> list[tuple[Path, str, str]]:
    source = source.expanduser().resolve()
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise DistributionError(f"Repository does not exist: {repo}")
    files = source_files(source)
    desired = fingerprints(files)
    selected = [name.strip().lower() for name in targets.split(",") if name.strip()]
    if not selected or any(name not in TARGETS for name in selected):
        raise DistributionError(f"Valid targets: {', '.join(TARGETS)}")
    folders = sorted({TARGETS[name] for name in selected})
    results: list[tuple[Path, str, str]] = []
    for folder in folders:
        dest = repo / folder / source.name
        # Do not follow symlinked installation roots outside the selected repo.
        segments = Path(folder).parts
        ancestor = repo
        symlinked_parent = False
        for segment in segments:
            ancestor = ancestor / segment
            if ancestor.is_symlink():
                symlinked_parent = True
                break
        if symlinked_parent:
            results.append((dest, "BLOCK", "installation parent is a symlink"))
        elif dest.resolve() == source:
            results.append((dest, "UNCHANGED", "target is canonical source"))
        else:
            action, explanation = target_state(dest, desired)
            results.append((dest, action, explanation))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Canonical skill directory")
    parser.add_argument("--repo", required=True, type=Path, help="Repository root")
    parser.add_argument("--targets", default="common", help="Comma-separated: common,claude,copilot,...")
    parser.add_argument("--apply", action="store_true", help="Actually write permitted copies")
    args = parser.parse_args()
    try:
        source = args.source.expanduser().resolve()
        repo = args.repo.expanduser().resolve()
        files = source_files(source)
        desired = fingerprints(files)
        items = plan(source, repo, args.targets)
        for dest, action, reason in items:
            print(f"{action}: {dest} ({reason})")
        if any(action == "BLOCK" for _, action, _ in items):
            print("BLOCKED: no changes were made", file=sys.stderr)
            return 1
        if not args.apply:
            print("DRY RUN: pass --apply for explicitly approved installation/synchronization")
            return 0
        for dest, action, _ in items:
            if action in {"CREATE", "UPDATE"}:
                install(source, dest, files, desired)
                print(f"APPLIED: {dest}")
        return 0
    except (DistributionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
