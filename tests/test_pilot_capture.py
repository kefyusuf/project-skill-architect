"""Real OS-subprocess validation (NOT a live Codex / Claude Code session)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import pilot_host
from pilot_lab import prepare


class BoundedHostProcessTests(unittest.TestCase):
    def invoke(self, code, timeout=5):
        return pilot_host.capture_bounded([sys.executable, '-c', code], Path.cwd(), os.environ.copy(), timeout)

    def test_real_subprocess_success_and_structured_output(self):
        result = self.invoke("print('{\"type\":\"turn.completed\"}')")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.overflow)
        self.assertEqual(pilot_host.summarize_stream('codex', result.stdout, result.returncode)['process_status'], 'completed')

    def test_real_subprocess_nonzero_is_not_success(self):
        result = self.invoke('import sys; sys.exit(7)')
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.timed_out)

    def test_real_subprocess_timeout_terminates(self):
        result = self.invoke('import time; time.sleep(5)', timeout=0.2)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.overflow)

    def test_stdout_is_rejected_during_streaming_not_after_full_capture(self):
        with patch.object(pilot_host, 'MAX_OUTPUT_BYTES', 64 * 1024):
            result = self.invoke('import sys; sys.stdout.buffer.write(b"x"*800000); sys.stdout.flush()')
        self.assertTrue(result.overflow)
        self.assertLessEqual(len(result.stdout), 64 * 1024)

    def test_no_raw_stdout_written_to_disk_by_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = 'import sys; sys.stdout.write("SECRET_MOCK_MESSAGE")'
            result = pilot_host.capture_bounded([sys.executable, '-c', code], Path(tmp), os.environ.copy(), 5)
            self.assertIn(b'SECRET_MOCK_MESSAGE', result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class EndToEndWithoutLiveAgent(unittest.TestCase):
    def test_real_host_runner_uses_disposable_fixture_and_no_result_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixtures = tmp / 'fixtures'
            prepare(fixtures)
            workspace = tmp / 'live-run'
            source = Path(__file__).resolve().parents[1]
            script = "print('{\"type\":\"turn.completed\"}')"
            with patch('pilot_host.shutil.which', return_value=sys.executable), \
                 patch('pilot_host.command', return_value=[sys.executable, '-c', script]):
                outcome = pilot_host.run(fixtures, workspace, 'codex', 'adopt-existing', source)
            self.assertEqual(outcome['process_status'], 'completed')
            self.assertEqual(outcome['observed'], 'unknown')
            self.assertTrue(outcome['workspace_unchanged'])
            self.assertFalse(outcome['pilot_result_written'])
            self.assertTrue((workspace / '.agents/skills/project-skill-architect/SKILL.md').is_file())


if __name__ == '__main__':
    unittest.main()
