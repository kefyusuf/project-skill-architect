#!/usr/bin/env python3
"""Lightweight, dependency-free structural checks for Agent Skills.

Usage: python validate.py PATH
PATH may be a single skill folder or a parent folder containing skill folders.
This does NOT replace YAML parsing or a runtime invocation test.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELDS = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*$")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def read_frontmatter(path: Path) -> tuple[dict[str, str], str, list[str]]:
    errors: list[str] = []
    data = path.read_text(encoding="utf-8-sig")
    lines = data.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        return {}, data, ["missing opening YAML frontmatter delimiter"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, data, ["missing closing YAML frontmatter delimiter"]
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found = FIELDS.match(line)
        if not found:
            errors.append(f"unsupported/invalid frontmatter line: {line[:70]}")
            continue
        key, value = found.groups()
        if key in fields:
            errors.append(f"duplicate frontmatter field: {key}")
        fields[key] = value.strip('"\'')
    return fields, "\n".join(lines[end + 1 :]), errors


def check(folder: Path) -> list[str]:
    issues: list[str] = []
    path = folder / "SKILL.md"
    if not path.is_file():
        return [f"{folder}: missing SKILL.md"]
    fields, body, errors = read_frontmatter(path)
    issues += [f"{path}: {e}" for e in errors]
    name = fields.get("name", "")
    desc = fields.get("description", "")
    if not name or len(name) > 64 or not NAME.fullmatch(name):
        issues.append(f"{path}: invalid or missing 'name'")
    elif name != folder.name:
        issues.append(f"{path}: name does not match folder '{folder.name}'")
    if not desc or len(desc) > 1024:
        issues.append(f"{path}: 'description' must be 1..1024 characters")
    if not body.strip():
        issues.append(f"{path}: empty instruction body")
    if "<kebab-case-name>" in body or "<What this skill" in body or name.startswith("<"):
        issues.append(f"{path}: template placeholders remain")
    for dest in LINK.findall(body):
        dest = dest.split("#", 1)[0].split("?", 1)[0].strip()
        if not dest or dest.startswith(("https://", "http://", "mailto:", "/")):
            continue
        if not (folder / dest).exists():
            issues.append(f"{path}: missing relative reference '{dest}'")
    return issues


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate.py <skill-folder-or-skills-parent>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    folders = [root] if (root / "SKILL.md").exists() else sorted(
        p for p in root.iterdir() if p.is_dir()
    )
    if not folders:
        print("No skill folders found", file=sys.stderr)
        return 1
    issues = [issue for folder in folders for issue in check(folder)]
    if issues:
        for issue in issues:
            print(f"FAIL {issue}")
        return 1
    print(f"PASS {len(folders)} skill(s) passed lightweight structural checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
