#!/usr/bin/env python3
"""Opt-in, privacy-bounded real-host pilot on v8.1 synthetic fixtures ONLY.

The default 'plan' command is read-only. 'run' requires --execute, creates a
fresh disposable workspace, and launches a locally installed coding agent.
Neither command writes pilot outcomes or asserts that a skill succeeded.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from distribute import DistributionError, fingerprints, install, plan as distribution_plan, source_files
from pilot_lab import CASES, LabError, _digest, stage, verify

MAX_OUTPUT_BYTES = 12 * 1024 * 1024
MAX_EVENTS = 20_000
TIMEOUT = 180
SKILL_NAME = 'project-skill-architect'


class HostPilotError(ValueError):
    pass


@dataclass(frozen=True)
class CaptureResult:
    """Bounded subprocess observations; never persist full host output."""
    returncode: int | None
    stdout: bytes
    timed_out: bool
    overflow: bool


def capture_bounded(cmd: list[str], cwd: Path, env: dict[str, str], timeout: float) -> CaptureResult:
    """Consume a real process incrementally; kill if time or stdout budget is exceeded.

    Unlike subprocess.run(..., stdout=PIPE), this limits retained stdout *while*
    the process is running, not after a potentially unbounded read. Stderr is
    discarded. This is a process boundary, NOT a hermetic host sandbox.
    """
    output = bytearray()
    overflow = threading.Event()
    reader_failed = threading.Event()
    process = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               bufsize=0)
    assert process.stdout is not None

    def read_output() -> None:
        try:
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                if len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                    overflow.set()
                    process.kill()
                    break
                output.extend(chunk)
        except (OSError, ValueError):
            reader_failed.set()
            if process.poll() is None:
                process.kill()

    reader = threading.Thread(target=read_output, daemon=True, name='host-output-reader')
    reader.start()
    timed_out = False
    try:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait(timeout=5)
        reader.join(timeout=5)
        if reader.is_alive() or reader_failed.is_set():
            raise HostPilotError('Unable to safely capture host output')
        return CaptureResult(process.returncode, bytes(output), timed_out, overflow.is_set())
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def command(host: str, prompt: str) -> list[str]:
    """Conservative command lines; no shell interpolation or write permission."""
    if host == 'codex':
        return ['codex', 'exec', '--json', '--ephemeral', '--ignore-user-config', '--sandbox', 'read-only', prompt]
    if host == 'claude':
        return ['claude', '-p', '--output-format', 'stream-json', '--verbose',
                '--no-session-persistence', '--permission-mode', 'plan',
                '--tools', 'Read,Glob,Grep,Skill', '--disallowedTools', 'mcp__*',
                '--max-turns', '6', prompt]
    raise HostPilotError('Only Codex and Claude Code have a reviewed runner')


def activation_signal(host: str, event: object) -> bool:
    """A named Skill tool invocation is positive evidence; prose is not.

    Codex JSON events currently do not document a portable dedicated skill
    activation event, so Codex stays unknown pending human host review.
    """
    if host != 'claude' or not isinstance(event, dict) or event.get('type') != 'assistant':
        return False
    msg = event.get('message')
    if not isinstance(msg, dict) or not isinstance(msg.get('content'), list):
        return False
    for block in msg['content']:
        if not isinstance(block, dict) or block.get('type') != 'tool_use' or block.get('name') != 'Skill':
            continue
        inp = block.get('input')
        if isinstance(inp, dict) and inp.get('skill') in (SKILL_NAME, f'/{SKILL_NAME}'):
            return True
    return False


def summarize_stream(host: str, raw: bytes, exit_code: int) -> dict:
    """Discard raw events immediately after classifying bounded metadata."""
    if len(raw) > MAX_OUTPUT_BYTES:
        raise HostPilotError('Host output exceeded safe in-memory limit')
    signal = False
    events = 0
    malformed = 0
    completed = False
    for line in raw.splitlines():
        if not line.strip():
            continue
        events += 1
        if events > MAX_EVENTS or len(line) > 256 * 1024:
            raise HostPilotError('Host event stream exceeds safe limits')
        try:
            item = json.loads(line)
        except (ValueError, UnicodeError):
            malformed += 1
            continue
        signal |= activation_signal(host, item)
        if isinstance(item, dict):
            if host == 'codex' and item.get('type') == 'turn.completed':
                completed = True
            if host == 'claude' and item.get('type') == 'result' and not item.get('is_error', False):
                completed = True
    return {
        'process_status': 'completed' if exit_code == 0 and completed else 'failed_or_unconfirmed',
        'exit_code': exit_code,
        'event_count': events,
        'malformed_event_count': malformed,
        'skill_activation': 'host_tool_signal' if signal else 'unknown',
        'observed': 'invoke' if signal else 'unknown',
        'verification': 'unknown',
        'skill_tokens': None,
        'warning': 'No activation signal does not prove skip. Host completion does not prove correct skill behavior.',
    }


def requirements(fixtures: Path, dest: Path, host: str, case: str, source: Path) -> dict:
    if case not in CASES:
        raise HostPilotError('Unknown pilot case')
    if host not in ('codex', 'claude'):
        raise HostPilotError('Unsupported host')
    verify(fixtures)
    if source.is_symlink() or not source.is_dir() or source.name != SKILL_NAME:
        raise HostPilotError('Source must be a real project-skill-architect folder')
    source_files(source)
    if not dest.parent.is_dir() or dest.exists() or dest.is_symlink():
        raise HostPilotError('Destination must be a new directory under an existing parent')
    # Never run inside the fixture tree or the source package itself.
    resolved = dest.resolve()
    if fixtures.resolve() == resolved or fixtures.resolve() in resolved.parents:
        raise HostPilotError('Cannot run inside immutable fixture templates')
    if source.resolve() == resolved or source.resolve() in resolved.parents:
        raise HostPilotError('Cannot run inside the canonical skill source')
    return {'host': host, 'case': case, 'expected': CASES[case][0],
            'workspace': str(dest), 'host_available': bool(shutil.which(host)),
            'will_launch': False, 'permissions': 'read-only / plan',
            'pilot_result_written': False, 'automatic_skill_grading': False}


def run(fixtures: Path, dest: Path, host: str, case: str, source: Path, timeout: int = TIMEOUT) -> dict:
    info = requirements(fixtures, dest, host, case, source)
    exe = shutil.which(host)
    if not exe:
        raise HostPilotError(f'{host} CLI not available; no live agent was launched')
    if not (10 <= timeout <= 600):
        raise HostPilotError('Timeout must be between 10 and 600 seconds')
    stage(fixtures, case, dest)
    target = 'claude' if host == 'claude' else 'common'
    target_path = dest / ('.claude/skills' if host == 'claude' else '.agents/skills') / SKILL_NAME
    try:
        decisions = distribution_plan(source, dest, target)
        if len(decisions) != 1 or decisions[0][1] != 'CREATE':
            raise HostPilotError('Skill installation is not a clean CREATE')
        files = source_files(source)
        install(source, target_path, files, fingerprints(files))
    except DistributionError as exc:
        raise HostPilotError('Skill could not be installed safely into disposable workspace') from exc
    if not target_path.joinpath('SKILL.md').is_file():
        raise HostPilotError('Expected installed skill not found')
    before = _digest(dest)
    cmd = command(host, CASES[case][1])
    cmd[0] = exe  # resolved host executable; fixed flags, no shell=True
    env = os.environ.copy()
    env['NO_COLOR'] = '1'
    env['CI'] = '1'
    capture = capture_bounded(cmd, dest, env, timeout)
    if capture.timed_out:
        result = {'process_status': 'timeout', 'exit_code': None,
                  'skill_activation': 'unknown', 'observed': 'unknown',
                  'verification': 'unknown', 'warning': 'Timed out; no result inferred'}
    elif capture.overflow:
        result = {'process_status': 'failed_or_unconfirmed', 'exit_code': capture.returncode,
                  'skill_activation': 'unknown', 'observed': 'unknown',
                  'verification': 'unknown', 'warning': 'Host output limit exceeded during capture; not evaluated'}
    else:
        result = summarize_stream(host, capture.stdout, capture.returncode)
    # No raw stdout, stderr, prompt, final answer, session transcript or tokens
    # written to a file or returned to the caller.
    return {**info, **result, 'will_launch': True, 'workspace_unchanged': before == _digest(dest),
            'pilot_result_written': False,
            'review': 'Confirm activation and task behavior independently; use pilot.py record only after review.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('plan', 'run'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--fixtures', required=True, type=Path)
        cmd.add_argument('--case', required=True, choices=tuple(CASES))
        cmd.add_argument('--host', required=True, choices=('codex', 'claude'))
        cmd.add_argument('--dest', required=True, type=Path)
        cmd.add_argument('--source', type=Path, default=Path(__file__).resolve().parent.parent)
        if name == 'run':
            cmd.add_argument('--execute', required=True, action='store_true')
            cmd.add_argument('--timeout', type=int, default=TIMEOUT)
    args = parser.parse_args(argv)
    try:
        if args.action == 'plan':
            result = requirements(args.fixtures, args.dest, args.host, args.case, args.source)
        else:
            result = run(args.fixtures, args.dest, args.host, args.case, args.source, args.timeout)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (HostPilotError, LabError, DistributionError, OSError, ValueError) as exc:
        # Avoid surfacing external CLI stderr or trace content.
        print(f'ERROR: {type(exc).__name__}: {str(exc)[:220]}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
