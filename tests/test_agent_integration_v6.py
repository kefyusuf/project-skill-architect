"""Opt-in host configuration must be compatible and never overwrite a prior install."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("integrate_v6", ROOT / "scripts/integrate.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HostConfigV6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        self.skill = self.repo / ".agents/skills/project-skill-architect"
        shutil.copytree(ROOT, self.skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def test_default_does_not_collect_any_events(self):
        for host in ("claude", "codex"):
            cfg = json.loads(mod.config_for(self.repo, host))
            self.assertEqual(list(cfg["hooks"]), ["SessionStart"])
            self.assertNotIn("agent_events.py", str(cfg))

    def test_explicit_opt_in_generates_correct_host_events(self):
        codex = json.loads(mod.config_for(self.repo, "codex", collect_failures=True))
        claude = json.loads(mod.config_for(self.repo, "claude", collect_failures=True))
        self.assertEqual(codex["hooks"]["PostToolUse"][0]["matcher"], "^Bash$")
        self.assertEqual(claude["hooks"]["PostToolUseFailure"][0]["hooks"][0]["type"], "command")
        self.assertIn("agent_events.py", str(codex))
        self.assertIn("agent_events.py", str(claude))

    def test_existing_v4_config_requires_manual_merge(self):
        path = self.repo / ".claude/settings.local.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = mod.config_for(self.repo, "claude")
        path.write_text(old)
        before = path.read_bytes()
        plan = mod.plan(self.repo, "claude", collect_failures=True)
        self.assertEqual(plan[0][2], "BLOCK")
        self.assertEqual(before, path.read_bytes())

    def test_preview_keeps_untracked_repos_unchanged(self):
        paths = mod.plan(self.repo, "codex,claude", collect_failures=True)
        self.assertEqual([p[2] for p in paths], ["CREATE", "CREATE"])
        self.assertFalse((self.repo / ".codex/hooks.json").exists())
        self.assertFalse((self.repo / ".claude/settings.local.json").exists())


if __name__ == "__main__":
    unittest.main()
