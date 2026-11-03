#!/usr/bin/env python3
"""v8: local, reviewer-driven pilot results for real coding-agent sessions.

No agent is launched. No prompts, command output, transcript, repository files,
API keys, user paths, or unverified cost estimates are collected. This is a
bounded metadata-only handoff to the v7 effectiveness evaluator.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from effectiveness import evaluate, validate as validate_suite, EffectivenessError

VERSION = 1
MAX_FILE = 128 * 1024
SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
HOSTS = {'codex', 'claude', 'cursor', 'gemini', 'opencode', 'other'}
PHASES = ('baseline', 'candidate')
CASE_DEFS = (
    ('bootstrap-project', 'invoke'),
    ('adopt-existing', 'invoke'),
    ('evolve-meaningful', 'invoke'),
    ('review-noop', 'invoke'),
    ('avoid-duplicate', 'invoke'),
    ('unrelated-bugfix', 'skip'),
    ('unrelated-writing', 'skip'),
    ('routine-code-change', 'skip'),
)
RESULT_FIELDS = {'phase', 'case_id', 'observed', 'verification', 'evidence', 'skill_tokens'}
FIELDS = {'schema_version', 'pilot_id', 'host', 'skill', 'cases', 'results'}


class PilotError(ValueError):
    """Invalid or unsafe pilot data."""


def slug(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not SLUG.fullmatch(raw):
        raise PilotError(f'{field} must be a short anonymous lowercase slug')
    return raw


def create(pilot_id: str, host: str, skill: str) -> dict[str, Any]:
    slug(pilot_id, 'pilot_id')
    slug(skill, 'skill')
    if not isinstance(host, str) or host not in HOSTS:
        raise PilotError('Unsupported host')
    return {'schema_version': VERSION, 'pilot_id': pilot_id, 'host': host,
            'skill': skill, 'cases': [{'id': name, 'expected': label} for name, label in CASE_DEFS],
            'results': []}


def validate(doc: object) -> dict[str, Any]:
    if not isinstance(doc, dict) or set(doc) != FIELDS or type(doc['schema_version']) is not int or doc['schema_version'] != VERSION:
        raise PilotError('Invalid pilot schema or unknown fields')
    template = create(doc['pilot_id'], doc['host'], doc['skill'])
    if doc['cases'] != template['cases']:
        raise PilotError('Pilot cases or expectations must not be edited')
    rows = doc['results']
    if not isinstance(rows, list) or len(rows) > 2 * len(CASE_DEFS):
        raise PilotError('Invalid number of results')
    seen = set()
    valid_cases = {x['id'] for x in template['cases']}
    for row in rows:
        if not isinstance(row, dict) or set(row) != RESULT_FIELDS:
            raise PilotError('Only the documented privacy-safe result fields are permitted')
        if not isinstance(row['phase'], str) or not isinstance(row['case_id'], str) or row['phase'] not in PHASES or row['case_id'] not in valid_cases:
            raise PilotError('Unknown phase or case')
        key = (row['phase'], row['case_id'])
        if key in seen:
            raise PilotError('Duplicate result; never silently replace prior measurements')
        seen.add(key)
    try:
        validate_suite(to_suite(doc))
    except EffectivenessError as exc:
        raise PilotError(str(exc)) from exc
    return doc


def to_suite(doc: dict[str, Any]) -> dict[str, Any]:
    # Materialize all missing cases as unknown, not successful/failed.
    recorded = {(r['phase'], r['case_id']): r for r in doc['results']}
    runs = []
    for phase in PHASES:
        for case in doc['cases']:
            row = recorded.get((phase, case['id']), {})
            runs.append({'phase': phase, 'host': doc['host'], 'skill': doc['skill'],
                         'case_id': case['id'], 'expected': case['expected'],
                         'observed': row.get('observed', 'unknown'),
                         'verification': row.get('verification', 'unknown'),
                         'evidence': row.get('evidence', 'none'),
                         'skill_tokens': row.get('skill_tokens')})
    return {'schema_version': 1, 'suite_id': doc['pilot_id'], 'runs': runs}


def record(doc: dict[str, Any], phase: str, case_id: str, observed: str,
           verification: str, evidence: str, tokens: int | None) -> None:
    validate(doc)
    if phase not in PHASES or case_id not in {c['id'] for c in doc['cases']}:
        raise PilotError('Unknown phase or case ID')
    if any(r['phase'] == phase and r['case_id'] == case_id for r in doc['results']):
        raise PilotError('Case already recorded; create a new pilot instead of overwriting evidence')
    row = {'phase': phase, 'case_id': case_id, 'observed': observed,
           'verification': verification, 'evidence': evidence, 'skill_tokens': tokens}
    proposed = {**doc, 'results': doc['results'] + [row]}
    validate(proposed)
    doc['results'].append(row)


def report(doc: dict[str, Any]) -> dict[str, Any]:
    validate(doc)
    progress = {}
    for phase in PHASES:
        rows = [r for r in doc['results'] if r['phase'] == phase]
        seen = [r for r in rows if r['observed'] != 'unknown']
        by_case = {c['id']: c['expected'] for c in doc['cases']}
        progress[phase] = {
            'total': len(doc['cases']),
            'recorded': len(seen),
            'unknown': len(doc['cases']) - len(seen),
            'verified': sum(r['verification'] == 'pass' for r in seen),
            'review_needed': sum(r['observed'] != by_case[r['case_id']] or
                                 r['verification'] == 'fail' for r in seen),
        }
    return {'pilot_id': doc['pilot_id'], 'host': doc['host'],
            'progress': progress, 'evaluation': evaluate(to_suite(doc)),
            'interpretation': 'Recorded means reviewer observed a case, not that skill was effective. '
                              'Unknown data never proves success. A clean candidate-only pilot '
                              'cannot establish improvement over a baseline.'}


def read_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise PilotError('File must be a bounded, regular JSON file (no symlinks)')
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError) as exc:
        raise PilotError('Unreadable pilot JSON') from exc
    return validate(doc)


def _encode(doc: dict[str, Any]) -> bytes:
    data = (json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(data) > MAX_FILE:
        raise PilotError('Pilot exceeds size limit')
    return data


def new_file(path: Path, doc: dict[str, Any]) -> None:
    validate(doc)
    if not path.parent.is_dir():
        raise PilotError('Output directory must already exist')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as dest:
            dest.write(_encode(doc))
            dest.flush()
            os.fsync(dest.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def add_to_file(path: Path, args: argparse.Namespace) -> None:
    lock = path.with_name(path.name + '.lock')
    if lock.is_symlink() or path.is_symlink():
        raise PilotError('Symlinked pilot file or lock is not allowed')
    fd = None
    temp = None
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        doc = read_file(path)
        record(doc, args.phase, args.case, args.observed, args.verification, args.evidence,
               args.skill_tokens)
        raw = _encode(doc)
        with tempfile.NamedTemporaryFile(mode='wb', prefix='.pilot-', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            os.chmod(temp, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise PilotError('Pilot file was replaced by a symlink')
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        if fd is not None:
            os.close(fd)
            lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create an empty scenario registry, never overwrites')
    init.add_argument('--file', required=True, type=Path)
    init.add_argument('--host', required=True, choices=sorted(HOSTS))
    init.add_argument('--skill', default='project-skill-architect')
    init.add_argument('--pilot-id', default='skill-pilot')
    rec = commands.add_parser('record', help='Record reviewer-observed metadata for one scenario')
    rec.add_argument('--file', required=True, type=Path)
    rec.add_argument('--phase', required=True, choices=PHASES)
    rec.add_argument('--case', required=True)
    rec.add_argument('--observed', required=True, choices=('invoke', 'skip', 'unknown'))
    rec.add_argument('--verification', default='unknown', choices=('pass', 'fail', 'unknown'))
    rec.add_argument('--evidence', default='none', choices=('host_trace', 'reviewed_manual', 'none'))
    rec.add_argument('--skill-tokens', type=int)
    review = commands.add_parser('report', help='Read-only progress and v7 evaluation')
    review.add_argument('--file', required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == 'init':
            new_file(args.file, create(args.pilot_id, args.host, args.skill))
            print(f'CREATED: {args.file}; all scenarios unobserved')
        elif args.command == 'record':
            add_to_file(args.file, args)
            print('RECORDED: one reviewer supplied result (not automatically verified)')
        else:
            print(json.dumps(report(read_file(args.file)), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (PilotError, EffectivenessError, OSError, ValueError) as exc:
        print(f'Pilot refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
