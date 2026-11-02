"""Integration tests: host configs are strictly opt-in and hooks are advisory."""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import integrate  # noqa: E402
import checkpoint  # noqa: E402
import hook_bridge  # noqa: E402
import ci_report  # noqa: E402


class IntegrationTests(unittest.TestCase):
    def repo_with_install(self, path: Path) -> Path:
        repo = path / "repo"
        skill = repo / integrate.SKILL_REL
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: project-skill-architect\n---", encoding="utf-8")
        for name in ("hook_bridge.py", "ci_report.py"):
            (skill / "scripts" / name).write_text("# test installation", encoding="utf-8")
        return repo

    def test_missing_skill_refuses_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(integrate.IntegrationError):
                integrate.plan(Path(tmp), "codex")

    def test_invalid_duplicate_host_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with_install(Path(tmp))
            with self.assertRaises(integrate.IntegrationError):
                integrate.plan(repo, "codex,codex")

    def test_dry_run_does_not_write_configs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with_install(Path(tmp))
            self.assertEqual(integrate.main(["--repo", str(repo)]), 0)
            self.assertFalse((repo / ".codex").exists())
            self.assertFalse((repo / ".claude").exists())
            self.assertFalse((repo / ".github").exists())

    def test_apply_creates_only_requested_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with_install(Path(tmp))
            self.assertEqual(integrate.main(["--repo", str(repo), "--hosts", "codex,claude", "--apply"]), 0)
            codex = json.loads((repo / ".codex/hooks.json").read_text(encoding="utf-8"))
            claude = json.loads((repo / ".claude/settings.local.json").read_text(encoding="utf-8"))
            self.assertIn("SessionStart", codex["hooks"])
            self.assertIn("SessionStart", claude["hooks"])
            self.assertFalse((repo / ".github").exists())
            self.assertEqual(integrate.main(["--repo", str(repo), "--hosts", "codex,claude", "--apply"]), 0)

    def test_existing_config_blocks_all_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with_install(Path(tmp))
            (repo / ".claude").mkdir()
            original = '{"permissions":{"deny":["Read(./.env)"]}}\n'
            (repo / ".claude/settings.local.json").write_text(original, encoding="utf-8")
            self.assertEqual(integrate.main(["--repo", str(repo), "--hosts", "codex,claude", "--apply"]), 1)
            self.assertFalse((repo / ".codex").exists())
            self.assertEqual((repo / ".claude/settings.local.json").read_text(encoding="utf-8"), original)

    def test_symlinked_target_parent_blocked(self):
        if os.name == "nt":
            self.skipTest("symlink permission not available on all Windows machines")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.repo_with_install(root)
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (repo / ".codex").symlink_to(elsewhere, target_is_directory=True)
            self.assertEqual(integrate.plan(repo, "codex")[0][2], "BLOCK")
            self.assertEqual(list(elsewhere.iterdir()), [])

    def test_workflow_is_readonly_with_pull_request_and_no_auto_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with_install(Path(tmp))
            self.assertEqual(integrate.main(["--repo", str(repo), "--hosts", "github", "--apply"]), 0)
            content = (repo / ".github/workflows/skill-architecture-check.yml").read_text(encoding="utf-8")
            self.assertIn("pull_request:", content)
            self.assertIn("contents: read", content)
            self.assertIn("persist-credentials: false", content)
            self.assertNotIn("pull_request_target:", content)
            self.assertNotIn("--save-baseline", content)
            self.assertNotIn("--apply", content)

    def test_hook_emits_nothing_without_approved_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{"hook_event_name":"SessionStart"}'))):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(hook_bridge.main(["--repo", str(repo), "--host", "codex"]), 0)
            self.assertEqual(output.getvalue(), "")

    def test_hook_only_suggests_changes_after_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "AGENTS.md").write_text("Original", encoding="utf-8")
            baseline = hook_bridge.git_local_baseline(repo)
            self.assertIsNotNone(baseline)
            checkpoint.save_baseline(baseline, checkpoint.snapshot(repo))
            (repo / "AGENTS.md").write_text("Revised", encoding="utf-8")
            for host in ("codex", "claude"):
                output = io.StringIO()
                with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{"hook_event_name":"SessionStart"}'))):
                    with redirect_stdout(output):
                        self.assertEqual(hook_bridge.main(["--repo", str(repo), "--host", host]), 0)
                content = output.getvalue()
                self.assertIn("AGENTS.md", content)
                self.assertIn("do not change skills", content)
                if host == "codex":
                    parsed = json.loads(content)
                    self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "SessionStart")
                else:
                    self.assertTrue(content.startswith("Project Skill Architect checkpoint"))
            self.assertEqual(checkpoint.snapshot(repo)["files"]["AGENTS.md"],
                             checkpoint.snapshot(repo)["files"]["AGENTS.md"])
            self.assertTrue(baseline.is_file())  # no implicit replace

    def test_hook_ignores_unrelated_source_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            base = hook_bridge.git_local_baseline(repo)
            checkpoint.save_baseline(base, checkpoint.snapshot(repo))
            (repo / "app.py").write_text("print(1)", encoding="utf-8")
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{}'))):
                result = io.StringIO()
                with redirect_stdout(result):
                    self.assertEqual(hook_bridge.main(["--repo", str(repo), "--host", "claude"]), 0)
            self.assertEqual(result.getvalue(), "")

    def test_hook_rejects_oversized_input_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'x' * (hook_bridge.MAX_INPUT + 1)))):
                result = io.StringIO()
                with redirect_stdout(result):
                    self.assertEqual(hook_bridge.main(["--repo", tmp, "--host", "codex"]), 0)
            self.assertEqual(result.getvalue(), "")

    def test_report_does_not_make_changes_and_sanitizes_paths(self):
        outcome = {"status": "review_suggested", "signals": [
            {"kind": "instruction", "paths": ["AGENTS.md", "a`b\n- malicious"]},
        ]}
        rendered = ci_report.markdown_report(outcome)
        self.assertIn("AGENTS.md", rendered)
        self.assertNotIn("\n- malicious", rendered)
        self.assertIn("No skills or baselines", rendered)

    def test_integration_files_are_checkpoint_relevant(self):
        self.assertEqual(checkpoint.classify(".codex/hooks.json"), "agent-integration")
        self.assertEqual(checkpoint.classify(".claude/settings.local.json"), "agent-integration")


if __name__ == "__main__":
    unittest.main()
