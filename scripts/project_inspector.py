#!/usr/bin/env python3
"""Read-only, bounded snapshot of a project's Agent Skills integration.

Usage: python project_inspector.py --repo /path/to/repository
Does not inspect secret files or application source code. No repository writes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

SKILL_ROOTS = (
    ".agents/skills", ".claude/skills", ".cursor/skills",
    ".gemini/skills", ".opencode/skills", ".github/skills",
)
INSTRUCTION_FILES = (
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
)
PROJECT_FILES = (
    "README.md", "composer.json", "package.json", "pyproject.toml", "requirements.txt",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Makefile",
)
CI_FILES = (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml")
MAX_SKILLS_PER_ROOT = 100
MAX_SKILL_BYTES = 16_384
FRONTMATTER_FIELD = re.compile(r"^(name|description):\s*(.*)$")


def brief_metadata(skill_path: Path) -> dict[str, str]:
    result = {"path": skill_path.as_posix()}
    try:
        with skill_path.open("rb") as handle:
            data = handle.read(MAX_SKILL_BYTES)
        lines = data.decode("utf-8-sig", errors="replace").splitlines()
        if not lines or lines[0].strip() != "---":
            result["metadata_warning"] = "missing frontmatter"
            return result
        for line in lines[1:]:
            if line.strip() == "---":
                break
            match = FRONTMATTER_FIELD.match(line)
            if match:
                key, value = match.groups()
                result[key] = value.strip().strip('"\'')[:1024]
    except (OSError, UnicodeError) as exc:
        result["metadata_warning"] = type(exc).__name__
    return result


def git_summary(repo: Path) -> dict[str, object]:
    try:
        cmd = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if cmd.returncode != 0:
            return {"available": False}
        return {"available": True, "tracked_changes_present": bool(cmd.stdout.strip())}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}


def inspect(repo: Path) -> dict[str, object]:
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")
    repo = repo.resolve()
    skills: dict[str, list[dict[str, str]]] = {}
    truncated: list[str] = []
    for rel in SKILL_ROOTS:
        root = repo / rel
        found: list[dict[str, str]] = []
        if root.is_dir() and not root.is_symlink():
            # One level is portable; some hosts support deeper nesting but not all.
            children = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name)
            if len(children) > MAX_SKILLS_PER_ROOT:
                truncated.append(rel)
            for folder in children[:MAX_SKILLS_PER_ROOT]:
                skill_file = folder / "SKILL.md"
                if skill_file.is_file() and not skill_file.is_symlink():
                    info = brief_metadata(skill_file)
                    info["path"] = skill_file.relative_to(repo).as_posix()
                    found.append(info)
        if root.exists():
            skills[rel] = found
    return {
        "repository": str(repo),
        "instructions": [p for p in INSTRUCTION_FILES if (repo / p).is_file()],
        "project_markers": [p for p in PROJECT_FILES if (repo / p).is_file()],
        "ci_markers": [p for p in CI_FILES if (repo / p).is_file()] +
                      ([".github/workflows"] if (repo / ".github/workflows").is_dir() else []),
        "skill_roots": skills,
        "truncated_roots": truncated,
        "git": git_summary(repo),
        "limitations": "Metadata-only snapshot of common roots; not a full workflow/host audit. No files changed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.repo)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
