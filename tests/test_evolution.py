"""Contract tests for read-only semantic evolution triage."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evolution", ROOT / "scripts/evolution.py")
evolution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evolution)


def observed(id="f1", *, kind="agent-failure", topic="deployment", occurrence="run-1", source="user", paths=None):
    value = {"id": id, "kind": kind, "topic": topic, "source": source,
             "summary": "Deployment workflow did not follow the agreed review gates",
             "evidence_paths": paths or []}
    if occurrence is not None:
        value["occurrence"] = occurrence
    return value


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()

    def assess(self, observations=None, checkpoint=None, decisions=None):
        return evolution.assess(self.repo, {"schema_version": 1, "observations": observations or []},
                                checkpoint=checkpoint, decisions=decisions)

    def test_single_failure_does_not_propose_new_skill(self):
        result = self.assess([observed()])
        self.assertEqual(result["status"], "watch")
        self.assertIsNone(result["recommendation"])

    def test_two_distinct_failure_occurrences_prompt_review_existing_workflow(self):
        result = self.assess([observed(), observed("f2", occurrence="run-2")])
        self.assertEqual(result["status"], "review_recommended")
        self.assertEqual(result["recommendation"]["decision"], "review_existing")
        self.assertEqual(result["recommendation"]["candidate_key"], "agent-failure:deployment")
        self.assertEqual(result["recommendation"]["evidence_ids"], ["f1", "f2"])
        self.assertNotIn("create_skill", result)

    def test_two_descriptions_of_same_occurrence_are_not_recurring(self):
        result = self.assess([observed(), observed("f2", occurrence="run-1")])
        self.assertEqual(result["status"], "watch")

    def test_failures_in_separate_workflows_do_not_combine(self):
        result = self.assess([observed(), observed("f2", topic="billing", occurrence="run-2")])
        self.assertEqual(result["status"], "watch")

    def test_new_service_without_repo_evidence_is_a_watch_signal_not_semantic_fact(self):
        result = self.assess([observed("s1", kind="new-service", topic="billing", occurrence=None,
                                       paths=["services/billing/README.md"])])
        self.assertEqual(result["status"], "watch")

    def test_user_reported_new_service_with_existing_path_prompts_review_not_generation(self):
        directory = self.repo / "services/billing"
        directory.mkdir(parents=True)
        (directory / "README.md").write_text("Billing\n")
        result = self.assess([observed("s1", kind="new-service", topic="billing", occurrence=None,
                                       paths=["services/billing/README.md"])])
        self.assertEqual(result["status"], "review_recommended")
        self.assertEqual(result["recommendation"]["decision"], "review_existing")
        self.assertEqual(result["recommendation"]["evidence_strength"], "user-reported-path-present")
        self.assertIn("not verified", result["limits"].lower())

    def test_unconfirmed_agent_claim_with_existing_path_remains_watch(self):
        (self.repo / "package.json").write_text("{}")
        result = self.assess([observed("a1", kind="architecture-change", topic="api",
                                       occurrence=None, source="agent", paths=["package.json"])])
        self.assertEqual(result["status"], "watch")

    def test_skill_change_checkpoint_prompts_review_but_ci_only_does_not(self):
        skill = self.repo / ".agents/skills/build/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: build\n---\n")
        change = {"status": "review_suggested", "signals": [{"kind": "skill", "paths": [str(skill.relative_to(self.repo))]}]}
        result = self.assess(checkpoint=change)
        self.assertEqual(result["status"], "review_recommended")
        self.assertEqual(result["recommendation"]["candidate_key"], "checkpoint:skill")
        only_ci = {"status": "review_suggested", "signals": [{"kind": "ci", "paths": [".github/workflows/test.yml"]}]}
        self.assertEqual(self.assess(checkpoint=only_ci)["status"], "watch")

    def test_no_changes_with_comparison_is_no_change(self):
        result = self.assess(checkpoint={"status": "no_relevant_change", "signals": []})
        self.assertEqual(result["status"], "no_change")

    def test_no_inputs_are_insufficient_evidence(self):
        self.assertEqual(self.assess()["status"], "insufficient_evidence")

    def test_only_one_priority_recommendation_per_checkpoint(self):
        (self.repo / "AGENTS.md").write_text("Rules")
        result = self.assess([observed(), observed("f2", occurrence="run-2")],
                             checkpoint={"status": "review_suggested", "signals": [
                                 {"kind": "instruction", "paths": ["AGENTS.md"]}]})
        self.assertEqual(result["recommendation"]["candidate_key"], "agent-failure:deployment")
        self.assertEqual(result["deferred_candidates"], 1)

    def test_multiple_reports_same_kind_and_topic_are_one_candidate(self):
        (self.repo / "AGENTS.md").write_text("Rules")
        reports = [observed("g1", kind="skill-gap", topic="release", occurrence=None,
                            paths=["AGENTS.md"]),
                   observed("g2", kind="skill-gap", topic="release", occurrence=None,
                            paths=["AGENTS.md"])]
        outcome = self.assess(reports)
        self.assertEqual(outcome["recommendation"]["candidate_key"], "skill-gap:release")
        self.assertEqual(outcome["recommendation"]["evidence_ids"], ["g1", "g2"])
        self.assertEqual(outcome["deferred_candidates"], 0)

    def test_changed_checkpoint_fingerprint_reopens_previously_reviewed_candidate(self):
        file = self.repo / "AGENTS.md"
        file.write_text("first")
        change = {"status": "review_suggested", "signals": [{"kind": "instruction", "paths": ["AGENTS.md"]}]}
        first = self.assess(checkpoint=change)["recommendation"]
        reviewed = {"schema_version": 1, "decisions": [{"candidate_key": first["candidate_key"],
                    "decision": "resolved", "evidence_ids": first["evidence_ids"]}]}
        self.assertEqual(self.assess(checkpoint=change, decisions=reviewed)["status"], "no_change")
        file.write_text("second")
        self.assertEqual(self.assess(checkpoint=change, decisions=reviewed)["status"], "review_recommended")

    def test_declined_candidate_is_suppressed_until_new_observation(self):
        entries = [observed(), observed("f2", occurrence="run-2")]
        original = self.assess(entries)["recommendation"]
        reviewed = {"schema_version": 1, "decisions": [{"candidate_key": original["candidate_key"],
                            "decision": "declined", "evidence_ids": original["evidence_ids"]}]}
        self.assertEqual(self.assess(entries, decisions=reviewed)["status"], "no_change")
        fresh = self.assess(entries + [observed("f3", occurrence="run-3")], decisions=reviewed)
        self.assertEqual(fresh["status"], "review_recommended")
        self.assertIn("f3", fresh["recommendation"]["evidence_ids"])

    def test_rejects_duplicate_ids_and_traversal(self):
        with self.assertRaises(evolution.EvolutionError):
            self.assess([observed(), observed()])
        with self.assertRaises(evolution.EvolutionError):
            self.assess([observed(paths=["../.env"])])

    def test_rejects_malformed_and_unbounded_input(self):
        with self.assertRaises(evolution.EvolutionError):
            evolution.assess(self.repo, {"schema_version": 9, "observations": []})
        with self.assertRaises(evolution.EvolutionError):
            evolution.assess(self.repo, {"schema_version": 1, "observations": [observed(str(i)) for i in range(101)]})
        with self.assertRaises(evolution.EvolutionError):
            self.assess([observed(kind="unknown")])

    def test_rejects_symlink_as_evidence(self):
        external = Path(self.tmp.name) / "external.txt"
        external.write_text("unrelated private material")
        symlink = self.repo / "link.txt"
        try:
            symlink.symlink_to(external)
        except OSError:
            self.skipTest("symlink unavailable on this system")
        result = self.assess([observed(kind="new-service", occurrence=None, paths=["link.txt"])])
        self.assertEqual(result["status"], "watch")

    def test_bad_checkpoint_and_decision_types_fail_safely(self):
        with self.assertRaises(evolution.EvolutionError):
            self.assess(checkpoint={"status": ["review_suggested"], "signals": []})
        with self.assertRaises(evolution.EvolutionError):
            self.assess(checkpoint={"status": "review_suggested", "signals": [
                {"kind": ["skill"], "paths": []}]})
        with self.assertRaises(evolution.EvolutionError):
            self.assess(decisions={"schema_version": 1, "decisions": [
                {"candidate_key": "agent-failure:deployment", "decision": [], "evidence_ids": ["f1"]}]})

    def test_cli_approved_baseline_detects_instruction_revision_without_mutation(self):
        rule = self.repo / "AGENTS.md"
        rule.write_text("initial", encoding="utf-8")
        baseline = Path(self.tmp.name) / "approved-baseline.json"
        baseline_cmd = subprocess.run([sys.executable, str(ROOT / "scripts/checkpoint.py"),
                "--repo", str(self.repo), "--save-baseline", str(baseline)],
                capture_output=True, text=True)
        self.assertEqual(baseline_cmd.returncode, 0, baseline_cmd.stderr)
        rule.write_text("revised", encoding="utf-8")
        before = rule.read_bytes()
        command = subprocess.run([sys.executable, str(ROOT / "scripts/evolution.py"),
                "--repo", str(self.repo), "--baseline", str(baseline)], capture_output=True, text=True)
        self.assertEqual(command.returncode, 0, command.stderr)
        payload = json.loads(command.stdout)
        self.assertEqual(payload["status"], "review_recommended")
        self.assertEqual(payload["recommendation"]["candidate_key"], "checkpoint:instruction")
        self.assertEqual(rule.read_bytes(), before)
        self.assertNotEqual(json.loads(baseline.read_text())["files"]["AGENTS.md"],
                            evolution._checkpoint.snapshot(self.repo)["files"]["AGENTS.md"])

    def test_cli_generates_json_without_repo_mutations(self):
        data = Path(self.tmp.name) / "observations.json"
        data.write_text(json.dumps({"schema_version": 1, "observations": [observed(), observed("f2", occurrence="run-2")]}))
        before = sorted(str(p.relative_to(self.repo)) for p in self.repo.rglob("*"))
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/evolution.py"), "--repo", str(self.repo),
                               "--observations", str(data)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "review_recommended")
        self.assertEqual(before, sorted(str(p.relative_to(self.repo)) for p in self.repo.rglob("*")))


if __name__ == "__main__":
    unittest.main()
