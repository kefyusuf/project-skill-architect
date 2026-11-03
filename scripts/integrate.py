#!/usr/bin/env python3
"""Opt-in host integration for approved, read-only skill-architecture checkpoints.

No changes by default. --apply creates missing host configs but never edits,
merges, removes, or overwrites existing configs. Local hooks use machine-specific
absolute interpreter and script paths; regenerate after moving a repository.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_REL = Path(".agents/skills/project-skill-architect")
HOST_PATHS = {
    "codex": Path(".codex/hooks.json"),
    "claude": Path(".claude/settings.local.json"),
    "github": Path(".github/workflows/skill-architecture-check.yml"),
}


class IntegrationError(ValueError):
    pass


def command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def config_for(repo: Path, host: str, *, collect_failures: bool = False) -> str:
    if host == "github":
        return """# Opt-in, advisory only. No pull_request_target, secrets, writes or PR comments.
name: Skill architecture checkpoint
on:
  pull_request:
permissions:
  contents: read
jobs:
  checkpoint:
    runs-on: ubuntu-latest
    steps:
      - name: Check out pull request
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - name: Compare approved project surfaces
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        run: |
          python3 .agents/skills/project-skill-architect/scripts/ci_report.py \\
            --repo . --since-ref "$BASE_SHA" > skill-checkpoint.md
          cat skill-checkpoint.md >> "$GITHUB_STEP_SUMMARY"
"""
    interpreter = sys.executable
    bridge = (repo / SKILL_REL / "scripts/hook_bridge.py").resolve()
    cmd = command([interpreter, str(bridge), "--repo", str(repo), "--host", host])
    hook = {"type": "command", "command": cmd, "timeout": 15}
    if host == "codex":
        hook["additionalContextLimit"] = 500
        data = {
            "description": "Advisory project skill architecture checkpoint; approved installation only.",
            "hooks": {"SessionStart": [{"hooks": [hook]}]},
        }
    else:
        data = {"hooks": {"SessionStart": [{"hooks": [hook]}]}}
    if collect_failures:
        observer = (repo / SKILL_REL / "scripts/agent_events.py").resolve()
        observe_cmd = command([interpreter, str(observer), "ingest", "--repo", str(repo), "--host", host])
        if host == "codex":
            data["hooks"]["PostToolUse"] = [{
                "matcher": "^Bash$",
                "hooks": [{"type": "command", "command": observe_cmd, "timeout": 5}],
            }]
        elif host == "claude":
            data["hooks"]["PostToolUseFailure"] = [{
                "hooks": [{"type": "command", "command": observe_cmd, "timeout": 5}],
            }]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def plan(repo: Path, hosts: str, *, collect_failures: bool = False) -> list[tuple[str, Path, str, str]]:
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise IntegrationError("Repository directory does not exist")
    source = repo / SKILL_REL
    if source.is_symlink() or not source.is_dir() or not (source / "SKILL.md").is_file():
        raise IntegrationError(
            "Install the canonical skill into .agents/skills/project-skill-architect first "
            "(using scripts/distribute.py with --targets common)."
        )
    trusted_components = [
        repo / ".agents", repo / ".agents/skills", source, source / "SKILL.md",
        source / "scripts", source / "scripts/hook_bridge.py", source / "scripts/ci_report.py",
    ]
    if any(p.is_symlink() for p in trusted_components):
        raise IntegrationError("Refusing a symlinked skill path or script")
    selected = [h.strip().lower() for h in hosts.split(",") if h.strip()]
    if not selected or len(selected) != len(set(selected)) or any(h not in HOST_PATHS for h in selected):
        raise IntegrationError(f"Choose unique hosts from {', '.join(HOST_PATHS)}")
    if collect_failures and any(h in ("codex", "claude") for h in selected):
        observer = source / "scripts/agent_events.py"
        if observer.is_symlink() or not observer.is_file():
            raise IntegrationError("Missing trusted agent_events.py for opt-in failure collection")
    for h in selected:
        if h in ("codex", "claude") and not (source / "scripts/hook_bridge.py").is_file():
            raise IntegrationError("Missing hook_bridge.py in installed skill")
        if h == "github" and not (source / "scripts/ci_report.py").is_file():
            raise IntegrationError("Missing ci_report.py in installed skill")
    results = []
    for h in selected:
        path = repo / HOST_PATHS[h]
        if any(parent.is_symlink() for parent in [path, *list(path.parents)[:-1]] if parent != repo and repo in parent.parents):
            results.append((h, path, "BLOCK", "symlink in target path"))
        elif path.exists():
            desired = config_for(repo, h, collect_failures=collect_failures)
            try:
                identical = path.is_file() and path.read_text(encoding="utf-8") == desired
            except (OSError, UnicodeError):
                identical = False
            results.append((h, path, "UNCHANGED" if identical else "BLOCK",
                            "already identical" if identical else "existing config; merge manually"))
        else:
            results.append((h, path, "CREATE", "not present"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--hosts", default="codex,claude,github")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--collect-failures", action="store_true",
                        help="Opt in to per-tool redacted failure metadata (local Git-private state)")
    args = parser.parse_args(argv)
    try:
        repo = args.repo.expanduser().resolve()
        entries = plan(repo, args.hosts, collect_failures=args.collect_failures)
        for host, path, state, note in entries:
            print(f"{state}: {host}: {path} ({note})")
        if any(e[2] == "BLOCK" for e in entries):
            print("BLOCKED: no files were changed", file=sys.stderr)
            return 1
        if not args.apply:
            print("DRY RUN: re-run with --apply only after reviewing the hooks and CI workflow")
            return 0
        for host, path, state, _ in entries:
            if state == "CREATE":
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(config_for(repo, host, collect_failures=args.collect_failures))
                print(f"CREATED: {path}")
        return 0
    except (IntegrationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
