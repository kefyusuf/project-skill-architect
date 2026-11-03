#!/usr/bin/env python3
"""Build and stage reproducible, entirely synthetic v8 pilot repositories.

No agent is launched, no user repository is read, no secrets or transcripts
are collected, and neither a pilot observation nor a pass is recorded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CASES = {
    'bootstrap-project': ('invoke', 'We are starting a new project. Determine what project skills are actually needed; ask only critical questions. Do not write files yet.'),
    'adopt-existing': ('invoke', 'Join this existing example repository. Inspect existing rules and skills before proposing changes; do not edit anything.'),
    'evolve-meaningful': ('invoke', 'We added a new deployment workflow and keep making the same release mistake. Should our skill architecture change? Provide evidence first.'),
    'review-noop': ('invoke', 'Review our skill architecture after a small unrelated code-only PR. Is any skill change actually justified?'),
    'avoid-duplicate': ('invoke', 'Our team wants an Agent Skill to support release readiness. Examine the existing project rules, skills, and repository evidence. Decide whether a new skill is justified, an existing skill should be revised, or no change is necessary. Explain the evidence. Do not modify files.'),
    'unrelated-bugfix': ('skip', 'Fix this failing unit test in the example application.'),
    'unrelated-writing': ('skip', 'Proofread this brief paragraph for grammar.'),
    'routine-code-change': ('skip', 'Rename a variable in the example application\'s test fixture.'),
}
SCHEMA = 2
IGNORE = {'pilot-lab.json'}


class LabError(ValueError):
    pass


def _git(repo: Path, *args: str) -> None:
    env = dict(os.environ)
    env['GIT_AUTHOR_NAME'] = 'Synthetic Fixture'
    env['GIT_AUTHOR_EMAIL'] = 'fixture@example.invalid'
    env['GIT_COMMITTER_NAME'] = 'Synthetic Fixture'
    env['GIT_COMMITTER_EMAIL'] = 'fixture@example.invalid'
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, env=env)
    if p.returncode:
        raise LabError(f'Git fixture setup failed ({args[0]}): {p.stderr[:240]}')


def _write(root: Path, path: str, content: str) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding='utf-8', newline='\n')


def _common(repo: Path, case: str) -> None:
    _write(repo, 'README.md', '# Synthetic test project\n\nDisposable fixture. No production code or secrets.\n')
    _write(repo, 'src/calculator.py', 'def add(left: int, right: int) -> int:\n    return left + right\n')
    _write(repo, 'tests/test_calculator.py', 'import unittest\nfrom src.calculator import add\n\nclass Tests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n')
    _write(repo, 'src/__init__.py', '')
    _write(repo, 'AGENTS.md', '# Synthetic project rules\n- Make minimal changes.\n- Do not add skills without a demonstrable recurring workflow.\n')
    if case != 'bootstrap-project':
        _write(repo, '.agents/skills/release-check/SKILL.md',
               '---\nname: release-check\ndescription: Use when reviewing the existing release checklist or repeated release mistakes.\n---\n\n# Release checklist\nVerify release steps, keep a short checklist and request approval before changing it.\n')
    if case == 'bootstrap-project':
        (repo / 'AGENTS.md').unlink()
    if case == 'unrelated-writing':
        _write(repo, 'docs/paragraph.txt', 'The developer have wrote a clear specification, but it need editing.\n')
    if case == 'unrelated-bugfix':
        _write(repo, 'src/calculator.py', 'def add(left: int, right: int) -> int:\n    return left - right  # synthetic defect\n')
    if case == 'routine-code-change':
        _write(repo, 'tests/test_calculator.py', 'import unittest\nfrom src.calculator import add\n\nclass Tests(unittest.TestCase):\n    def test_add(self):\n        first_value = 2\n        self.assertEqual(add(first_value, 3), 5)\n')
    if case in ('evolve-meaningful', 'review-noop'):
        _write(repo, 'docs/changes.md', '# Synthetic change history\nInitial configuration.\n')


def _generate_repo(repo: Path, case: str) -> None:
    repo.mkdir(parents=True)
    _common(repo, case)
    _git(repo, 'init', '-q')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-qm', 'fixture: synthetic base')
    if case == 'evolve-meaningful':
        _write(repo, '.github/workflows/release.yml',
               'name: Synthetic Release\non: workflow_dispatch\njobs:\n  dry-run:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo synthetic\n')
        _write(repo, 'docs/changes.md', '# Synthetic change history\nNew deployment workflow was introduced.\n')
        _write(repo, 'docs/incidents.md',
               '# Fictional incidents — not real production evidence\nTwo separate mock release sessions omitted the verification step.\nNo independent host trace is supplied.\n')
    if case == 'review-noop':
        _write(repo, 'src/calculator.py', 'def add(left: int, right: int) -> int:\n    result = left + right\n    return result\n')
        # No architecture or instruction changes, merely an implementation refactor.
    if case in ('evolve-meaningful', 'review-noop'):
        _git(repo, 'add', '.')
        _git(repo, 'commit', '-qm', 'fixture: synthetic change')


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    files = []
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(part == '.git' for part in rel.parts) or rel.as_posix() in IGNORE:
            continue
        if path.is_symlink():
            raise LabError('Fixture symlinks are prohibited')
        if path.is_file():
            files.append((rel.as_posix(), path))
    for name, path in sorted(files):
        h.update(name.encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
    return h.hexdigest()


def _read_manifest(fixtures: Path) -> dict:
    path = fixtures / 'pilot-lab.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32_768:
        raise LabError('Missing or unsafe lab manifest')
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise LabError('Unreadable lab manifest') from exc
    if not isinstance(doc, dict) or set(doc) != {'schema_version', 'cases'} or doc['schema_version'] != SCHEMA:
        raise LabError('Unexpected lab manifest schema')
    if not isinstance(doc['cases'], dict) or set(doc['cases']) != set(CASES):
        raise LabError('Incomplete lab fixture set')
    for case, (expected, prompt) in CASES.items():
        row = doc['cases'][case]
        if not isinstance(row, dict) or set(row) != {'expected', 'prompt', 'sha256'} or row['expected'] != expected or row['prompt'] != prompt:
            raise LabError(f'Invalid fixture entry: {case}')
        if not isinstance(row['sha256'], str) or len(row['sha256']) != 64:
            raise LabError('Invalid digest entry')
    return doc


def verify(fixtures: Path) -> dict:
    doc = _read_manifest(fixtures)
    for case in CASES:
        repo = fixtures / case
        if repo.is_symlink() or not repo.is_dir():
            raise LabError(f'Missing or unsafe fixture: {case}')
        if _digest(repo) != doc['cases'][case]['sha256']:
            raise LabError(f'Fixture modified: {case}; rebuild in a fresh directory')
    return {'status': 'ready', 'fixture_count': len(CASES), 'observed_agent_sessions': 0}


def prepare(destination: Path) -> dict:
    if not shutil.which('git'):
        raise LabError('Git is required to construct reproducible commit history')
    if not destination.parent.is_dir():
        raise LabError('Destination parent directory does not exist')
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise LabError('Destination already exists; refusing overwrite') from exc
    try:
        manifest = {'schema_version': SCHEMA, 'cases': {}}
        for case, (expected, prompt) in CASES.items():
            repo = destination / case
            _generate_repo(repo, case)
            manifest['cases'][case] = {'expected': expected, 'prompt': prompt, 'sha256': _digest(repo)}
        (destination / 'pilot-lab.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return verify(destination)
    except Exception:
        shutil.rmtree(destination)
        raise


def stage(fixtures: Path, case: str, destination: Path) -> dict:
    if case not in CASES:
        raise LabError('Unknown pilot case')
    verify(fixtures)
    if not destination.parent.is_dir():
        raise LabError('Destination parent directory does not exist')
    if destination.exists() or destination.is_symlink():
        raise LabError('Stage destination already exists; refusing overwrite')
    # Ensure the validated source and destination are not nested within each other.
    src = (fixtures / case).resolve()
    target = destination.resolve()
    if src == target or src in target.parents:
        raise LabError('Cannot stage within a fixture')
    shutil.copytree(src, destination, symlinks=False)
    return {'status': 'staged', 'case': case, 'expected': CASES[case][0],
            'prompt': CASES[case][1], 'workspace': str(destination),
            'observed_agent_sessions': 0,
            'next': 'Install reviewed skill on the target host and run this prompt in a NEW session. Record evidence manually with pilot.py.'}


def preflight(repo: Path, host: str) -> dict:
    if not repo.is_dir():
        raise LabError('Missing pilot workspace')
    if host not in ('codex', 'claude'):
        raise LabError('Unsupported preflight host')
    skill = repo / ('.agents/skills/project-skill-architect/SKILL.md' if host == 'codex' else '.claude/skills/project-skill-architect/SKILL.md')
    cmd = shutil.which(host)
    return {'host': host, 'cli_available': bool(cmd), 'skill_file_present': skill.is_file(),
            'status': 'local_setup_detected' if cmd and skill.is_file() else 'manual_setup_required',
            'activation_verified': False,
            'note': 'CLI availability and a skill file do not prove host discovery or automatic invocation.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='Create eight fresh Git fixture repositories')
    p.add_argument('--out', type=Path, required=True)
    v = commands.add_parser('verify', help='Check integrity of all untouched fixture templates')
    v.add_argument('--fixtures', type=Path, required=True)
    s = commands.add_parser('stage', help='Copy a clean case into a new disposable workspace')
    s.add_argument('--fixtures', type=Path, required=True)
    s.add_argument('--case', choices=tuple(CASES), required=True)
    s.add_argument('--dest', type=Path, required=True)
    c = commands.add_parser('preflight', help='Check local host setup without launching it')
    c.add_argument('--repo', type=Path, required=True)
    c.add_argument('--host', choices=('codex', 'claude'), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.out)
        elif args.command == 'verify':
            result = verify(args.fixtures)
        elif args.command == 'stage':
            result = stage(args.fixtures, args.case, args.dest)
        else:
            result = preflight(args.repo, args.host)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (LabError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
