"""v8.2: opt-in live-host bridge, tested without claiming real host access."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import pilot_host as runner
from pilot_lab import prepare


class HostCommandTests(unittest.TestCase):
    def test_codex_read_only(self):
        cmd = runner.command('codex', 'hello')
        self.assertIn('read-only', cmd)
        self.assertIn('--ephemeral', cmd)
        self.assertIn('--json', cmd)
        self.assertNotIn('workspace-write', cmd)
        self.assertEqual(cmd[-1], 'hello')

    def test_codex_windows_backend_is_explicit_without_relaxing_read_only(self):
        cmd = runner.command('codex', 'hello', platform='win32')
        self.assertEqual(cmd[cmd.index('-c') + 1], 'windows.sandbox="elevated"')
        self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'read-only')
        self.assertIn('--ignore-user-config', cmd)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)

    def test_nonwindows_codex_omits_windows_backend(self):
        cmd = runner.command('codex', 'hello', platform='linux')
        self.assertNotIn('-c', cmd)
        self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'read-only')

    def test_codex_successful_tool_event_is_not_skill_activation(self):
        raw = (b'{"type":"item.completed","item":{"type":"command_execution",'
               b'"status":"completed","exit_code":0}}\n{"type":"turn.completed"}\n')
        result = runner.summarize_stream('codex', raw, 0)
        self.assertEqual(result['tool_access'], 'command_executed')
        self.assertEqual(result['successful_command_count'], 1)
        self.assertEqual(result['skill_activation'], 'unknown')
        self.assertEqual(result['verification'], 'unknown')

    def test_claude_plan_mode(self):
        cmd = runner.command('claude', 'hello')
        self.assertIn('plan', cmd)
        self.assertIn('stream-json', cmd)
        self.assertIn('--max-turns', cmd)
        self.assertNotIn('--dangerously-skip-permissions', cmd)

    def test_reject_unknown_host(self):
        with self.assertRaises(runner.HostPilotError):
            runner.command('other', 'hello')

    def test_ignore_assistant_claims(self):
        event = {'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': 'I used project-skill-architect!'}]}}
        self.assertFalse(runner.activation_signal('claude', event))

    def test_accept_explicit_claude_skill_tool(self):
        event = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'project-skill-architect'}}]}}
        self.assertTrue(runner.activation_signal('claude', event))
        self.assertFalse(runner.activation_signal('codex', event))

    def test_do_not_confuse_ordinary_tool_with_skill(self):
        event = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/tmp/project-skill-architect/SKILL.md'}}]}}
        self.assertFalse(runner.activation_signal('claude', event))

    def test_unknown_absence_even_if_completed(self):
        raw = b'{"type":"turn.completed","usage":{"input_tokens":125}}\n'
        result = runner.summarize_stream('codex', raw, 0)
        self.assertEqual(result['process_status'], 'completed')
        self.assertEqual(result['observed'], 'unknown')
        self.assertIsNone(result['skill_tokens'])

    def test_codex_failed_command_prevents_false_completed_pilot(self):
        events = [
            {'type': 'item.completed', 'item': {
                'type': 'command_execution', 'status': 'failed',
                'exit_code': 1, 'aggregated_output': 'rg: Access is denied.'}},
            {'type': 'item.completed', 'item': {
                'type': 'command_execution', 'status': 'completed',
                'exit_code': 0, 'aggregated_output': '# Synthetic rules'}},
            {'type': 'turn.completed'},
        ]
        raw = ('\n'.join(json.dumps(event) for event in events) + '\n').encode()
        result = runner.summarize_stream('codex', raw, 0)
        self.assertEqual(result['process_status'], 'failed_or_unconfirmed')
        self.assertEqual(result['tool_access'], 'access_denied')
        self.assertEqual(result['successful_command_count'], 1)
        self.assertEqual(result['failed_command_count'], 1)
        self.assertEqual(result['skill_activation'], 'unknown')

    def test_codex_access_denied_inside_zero_exit_command_is_detected(self):
        events = [
            {'type': 'item.completed', 'item': {
                'type': 'command_execution', 'status': 'completed', 'exit_code': 0,
                'aggregated_output': 'Get-Content : Access is denied'}},
            {'type': 'turn.completed'},
        ]
        result = runner.summarize_stream(
            'codex', ('\n'.join(json.dumps(event) for event in events) + '\n').encode(), 0)
        self.assertEqual(result['process_status'], 'failed_or_unconfirmed')
        self.assertEqual(result['tool_access'], 'access_denied')
        self.assertEqual(result['failed_command_count'], 0)
        self.assertEqual(result['verification'], 'unknown')

    def test_trace_invocation_does_not_prove_pass(self):
        raw = json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'project-skill-architect'}}]}}).encode()
        raw += b'\n{"type":"result","is_error":false}\n'
        result = runner.summarize_stream('claude', raw, 0)
        self.assertEqual(result['observed'], 'invoke')
        self.assertEqual(result['verification'], 'unknown')
        self.assertEqual(result['process_status'], 'completed')

    def test_bounds_event_size(self):
        with self.assertRaises(runner.HostPilotError):
            runner.summarize_stream('codex', b'A' * (256 * 1024 + 1), 0)

    def test_failure_not_success(self):
        self.assertEqual(runner.summarize_stream('claude', b'{"type":"result","is_error":true}\n', 1)['process_status'], 'failed_or_unconfirmed')


class LiveIntegrationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fixtures = self.base / 'fixtures'
        prepare(self.fixtures)
        self.dest = self.base / 'run'

    def test_plan_is_read_only(self):
        result = runner.requirements(self.fixtures, self.dest, 'codex', 'adopt-existing', self.source)
        self.assertFalse(self.dest.exists())
        self.assertFalse(result['will_launch'])
        self.assertFalse(result['pilot_result_written'])

    def test_plan_refuses_fixture_destination(self):
        with self.assertRaises(runner.HostPilotError):
            runner.requirements(self.fixtures, self.fixtures / 'scratch', 'claude', 'adopt-existing', self.source)

    def test_run_requires_cli_before_staging(self):
        with patch('pilot_host.shutil.which', return_value=None):
            with self.assertRaises(runner.HostPilotError):
                runner.run(self.fixtures, self.dest, 'codex', 'adopt-existing', self.source)
        self.assertFalse(self.dest.exists())

    def test_fake_host_runs_on_disposable_copy_only(self):
        args_seen = []
        def fake_capture(cmd, cwd, env, timeout):
            args_seen.append((cmd, cwd, env, timeout))
            return runner.CaptureResult(0, b'{"type":"turn.completed"}\n', False, False)
        with patch('pilot_host.shutil.which', return_value='/opt/fake/codex'), patch('pilot_host.capture_bounded', side_effect=fake_capture):
            result = runner.run(self.fixtures, self.dest, 'codex', 'adopt-existing', self.source)
        self.assertEqual(result['observed'], 'unknown')
        self.assertEqual(result['verification'], 'unknown')
        self.assertEqual(result['process_status'], 'completed')
        self.assertTrue(result['workspace_unchanged'])
        self.assertTrue((self.dest / '.agents/skills/project-skill-architect/SKILL.md').is_file())
        self.assertEqual(args_seen[0][1], self.dest)
        self.assertEqual(args_seen[0][0][0], '/opt/fake/codex')

    def test_timeout_stays_unknown(self):
        def too_slow(cmd, cwd, env, timeout):
            return runner.CaptureResult(None, b'', True, False)
        with patch('pilot_host.shutil.which', return_value='/opt/fake/claude'), patch('pilot_host.capture_bounded', side_effect=too_slow):
            result = runner.run(self.fixtures, self.dest, 'claude', 'bootstrap-project', self.source, 10)
        self.assertEqual(result['process_status'], 'timeout')
        self.assertEqual(result['observed'], 'unknown')

    def test_cli_plan_default_no_execution(self):
        with patch('pilot_host.shutil.which', return_value=None):
            rc = runner.main(['plan', '--fixtures', str(self.fixtures), '--case', 'review-noop',
                              '--host', 'claude', '--dest', str(self.dest)])
        self.assertEqual(rc, 0)
        self.assertFalse(self.dest.exists())

    def test_run_cli_must_supply_execute(self):
        with self.assertRaises(SystemExit) as exc:
            runner.main(['run', '--fixtures', str(self.fixtures), '--case', 'review-noop',
                         '--host', 'codex', '--dest', str(self.dest)])
        self.assertEqual(exc.exception.code, 2)
        self.assertFalse(self.dest.exists())


if __name__ == '__main__':
    unittest.main()
