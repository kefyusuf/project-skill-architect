"""Privacy, opt-in collection, idempotency, and v5 handoff contracts."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agent_events", ROOT / "scripts/agent_events.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def payload(host, session="session-A", call="call-A", *, status=1, interrupt=False, cwd=""):
    event = {"cwd": cwd, "session_id": session, "tool_use_id": call,
             "tool_name": "Bash", "tool_input": {"command": "SECRET_KEY=private"},
             "tool_response": {"exit_code": status, "stdout": "authorization: bearer token"},
             "error": "very sensitive error message", "transcript_path": "/private/chat.json"}
    if host == "codex":
        event["hook_event_name"] = "PostToolUse"
    else:
        event["hook_event_name"] = "PostToolUseFailure"
        event["is_interrupt"] = interrupt
    return event


class EventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)

    def event(self, host="claude", **kwargs):
        return payload(host, cwd=str(self.repo), **kwargs)

    def test_no_automatic_state_from_read_only_inspect(self):
        self.assertEqual(mod.inspect(self.repo)["events"], 0)
        self.assertFalse(mod._state_path(self.repo).exists())

    def test_untrusted_fields_never_saved(self):
        result = mod.ingest(self.repo, "claude", self.event())
        self.assertEqual(result["status"], "recorded")
        data = mod._state_path(self.repo).read_text()
        for sensitive in ["SECRET_KEY", "private", "bearer", "token", "session-A", "call-A",
                          "transcript", "very sensitive", "tool_input", "tool_response"]:
            self.assertNotIn(sensitive, data)
        self.assertEqual(mod.inspect(self.repo)["by_category"], {"shell": 1})
        recent = mod.inspect(self.repo)["recent_events"]
        self.assertEqual(recent[0]["id"], result["event_id"])
        self.assertIn("session", recent[0])
        self.assertEqual(recent[0]["category"], "shell")
        self.assertFalse((self.repo / "project-skill-architect").exists())

    def test_duplicate_call_is_idempotent(self):
        self.assertEqual(mod.ingest(self.repo, "claude", self.event())["status"], "recorded")
        self.assertEqual(mod.ingest(self.repo, "claude", self.event())["status"], "duplicate")
        self.assertEqual(mod.inspect(self.repo)["events"], 1)

    def test_ignored_codex_success_and_ambiguous_response(self):
        self.assertEqual(mod.ingest(self.repo, "codex", self.event("codex", status=0))["status"], "ignored")
        bad = self.event("codex")
        bad["tool_response"] = "exit code 1 maybe"
        self.assertEqual(mod.ingest(self.repo, "codex", bad)["status"], "ignored")
        self.assertEqual(mod.inspect(self.repo)["events"], 0)

    def test_codex_nonzero_structured_exit_is_recorded(self):
        self.assertEqual(mod.ingest(self.repo, "codex", self.event("codex"))["status"], "recorded")

    def test_claude_interrupt_is_ignored(self):
        self.assertEqual(mod.ingest(self.repo, "claude", self.event(interrupt=True))["status"], "ignored")
        self.assertFalse(mod._state_path(self.repo).exists())

    def test_outside_cwd_is_ignored(self):
        outside = self.event()
        outside["cwd"] = self.tmp.name
        self.assertEqual(mod.ingest(self.repo, "claude", outside)["status"], "ignored")

    def test_repeat_in_same_session_is_not_sufficient(self):
        a = mod.ingest(self.repo, "claude", self.event(call="call-1"))["event_id"]
        b = mod.ingest(self.repo, "claude", self.event(call="call-2"))["event_id"]
        with self.assertRaisesRegex(mod.EventError, "independent sessions"):
            mod.evaluate(self.repo, "deploy-workflow", [a, b])

    def test_two_sessions_require_manual_topic_but_only_review_existing(self):
        a = mod.ingest(self.repo, "claude", self.event(session="s1", call="a"))["event_id"]
        b = mod.ingest(self.repo, "codex", self.event("codex", session="s2", call="b"))["event_id"]
        output = mod.evaluate(self.repo, "deploy-workflow", [a, b])
        self.assertEqual(output["status"], "review_recommended")
        self.assertEqual(output["recommendation"]["decision"], "review_existing")
        self.assertEqual(output["recommendation"]["candidate_key"], "agent-failure:deploy-workflow")
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_suppressed_evidence_stays_suppressed(self):
        a = mod.ingest(self.repo, "claude", self.event(session="s1", call="a"))["event_id"]
        b = mod.ingest(self.repo, "claude", self.event(session="s2", call="b"))["event_id"]
        decisions = {"schema_version": 1, "decisions": [{
            "candidate_key": "agent-failure:deploy-workflow", "decision": "declined", "evidence_ids": [a,b]
        }]}
        self.assertEqual(mod.evaluate(self.repo, "deploy-workflow", [a,b], decisions)["status"], "no_change")

    def test_missing_or_duplicate_event_ids_rejected(self):
        a = mod.ingest(self.repo, "claude", self.event())["event_id"]
        with self.assertRaises(mod.EventError):
            mod.evaluate(self.repo, "deploy", [a,a])
        with self.assertRaises(mod.EventError):
            mod.evaluate(self.repo, "deploy", [a,"0"*24])

    def test_mixed_categories_rejected(self):
        a = mod.ingest(self.repo, "claude", self.event(session="s1",call="x"))["event_id"]
        other = self.event(session="s2",call="y")
        other["tool_name"] = "Edit"
        b = mod.ingest(self.repo, "claude", other)["event_id"]
        with self.assertRaisesRegex(mod.EventError, "Mixed"):
            mod.evaluate(self.repo, "workflow", [a,b])

    def test_symlinked_ledger_rejected(self):
        path = mod._state_path(self.repo)
        path.parent.mkdir()
        real = Path(self.tmp.name) / "outside.txt"
        real.write_text("important")
        try:
            path.symlink_to(real)
        except (NotImplementedError, OSError):
            self.skipTest("Cannot create symlinks here")
        with self.assertRaises(mod.EventError):
            mod.ingest(self.repo, "claude", self.event())
        self.assertEqual(real.read_text(), "important")

    def test_cli_hook_is_silent_and_safe_on_malformed_input(self):
        run = subprocess.run([sys.executable, str(ROOT / "scripts/agent_events.py"), "ingest",
                              "--repo", str(self.repo), "--host", "claude"],
                             input="not JSON", text=True, capture_output=True)
        self.assertEqual(run.returncode, 0)
        self.assertFalse(run.stdout)
        self.assertFalse(run.stderr)

    def test_local_ledger_retention_bounded(self):
        for n in range(mod.MAX_EVENTS + 5):
            result = mod.ingest(self.repo, "claude", self.event(session=f"s{n}", call=f"c{n}"))
            self.assertEqual(result["status"], "recorded")
        self.assertEqual(mod.inspect(self.repo)["events"], mod.MAX_EVENTS)
        self.assertEqual(mod.inspect(self.repo)["distinct_sessions"], mod.MAX_EVENTS)


if __name__ == "__main__":
    unittest.main()
