import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checkpoint", ROOT / "scripts/checkpoint.py")
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


class CheckpointTests(unittest.TestCase):
    def test_expected_path_classification_with_dot_directories(self):
        self.assertEqual(checkpoint.classify(".agents/skills/test/SKILL.md"), "skill")
        self.assertEqual(checkpoint.classify(".claude/skills/test/references/usage.md"), "skill")
        self.assertEqual(checkpoint.classify(".github/workflows/build.yml"), "ci")
        self.assertEqual(checkpoint.classify(".github/copilot-instructions.md"), "instruction")
        self.assertIsNone(checkpoint.classify("src/app.py"))
        self.assertIsNone(checkpoint.classify(".env"))
        self.assertIsNone(checkpoint.classify(".agents/skills/test/data/private.env"))

    def test_initial_without_evidence_never_claims_no_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome = checkpoint.evaluate(Path(tmp))
            self.assertEqual(outcome["status"], "insufficient_evidence")
            self.assertEqual(outcome["signals"], [])

    def test_explicit_architecture_event_is_review_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome = checkpoint.evaluate(Path(tmp), event="architecture")
            self.assertEqual(outcome["status"], "review_suggested")
            self.assertEqual(outcome["signals"][0]["strength"], "user-or-host-declared-not-independently-verified")

    def test_same_baseline_is_no_change_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "AGENTS.md").write_text("Rules", encoding="utf-8")
            state = checkpoint.snapshot(repo)
            baseline = Path(tmp) / "baseline.json"
            checkpoint.save_baseline(baseline, state)
            before = set(repo.rglob("*"))
            outcome = checkpoint.evaluate(repo, baseline=baseline, event="pr")
            self.assertEqual(outcome["status"], "no_relevant_change")
            self.assertEqual(set(repo.rglob("*")), before)

    def test_instruction_change_produces_one_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            path = repo / "AGENTS.md"
            path.write_text("Initial", encoding="utf-8")
            baseline = Path(tmp) / "checkpoint.json"
            checkpoint.save_baseline(baseline, checkpoint.snapshot(repo))
            path.write_text("Modified", encoding="utf-8")
            result = checkpoint.evaluate(repo, baseline=baseline)
            self.assertEqual(result["status"], "review_suggested")
            self.assertEqual(result["signals"][0]["kind"], "instruction")
            self.assertEqual(result["signals"][0]["paths"], ["AGENTS.md"])

    def test_skill_and_workflow_changes_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            baseline = repo.parent / (repo.name + ".baseline")
            try:
                checkpoint.save_baseline(baseline, checkpoint.snapshot(repo))
                skill = repo / ".agents/skills/ship"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text("---\nname: ship\n---", encoding="utf-8")
                (skill / "references").mkdir()
                (skill / "references/flow.md").write_text("Flow", encoding="utf-8")
                flow = repo / ".github/workflows"
                flow.mkdir(parents=True)
                (flow / "ci.yml").write_text("name: Checks", encoding="utf-8")
                result = checkpoint.evaluate(repo, baseline=baseline)
                self.assertEqual({x["kind"] for x in result["signals"]}, {"skill", "ci"})
            finally:
                baseline.unlink(missing_ok=True)

    def test_generic_source_edit_does_not_produce_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            baseline = repo / "checkpoint-state.json"
            checkpoint.save_baseline(baseline, checkpoint.snapshot(repo))
            (repo / "src").mkdir()
            (repo / "src/app.py").write_text("print('hello')", encoding="utf-8")
            self.assertEqual(checkpoint.evaluate(repo, baseline=baseline)["status"], "no_relevant_change")

    def test_untrusted_baseline_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "bad.json"
            fake.write_text(json.dumps({"schema_version": 1, "files": {".env": "0" * 64}}), encoding="utf-8")
            with self.assertRaises(checkpoint.CheckpointError):
                checkpoint.evaluate(root, baseline=fake)

    def test_existing_baseline_needs_explicit_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "baseline.json"
            checkpoint.save_baseline(target, checkpoint.snapshot(root))
            with self.assertRaises(checkpoint.CheckpointError):
                checkpoint.save_baseline(target, checkpoint.snapshot(root))
            checkpoint.save_baseline(target, checkpoint.snapshot(root), replace=True)

    def test_incomplete_snapshot_cannot_be_used_to_claim_no_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            big = repo / "AGENTS.md"
            big.write_bytes(b"a" * (checkpoint.MAX_BYTES + 1))
            state = checkpoint.snapshot(repo)
            self.assertTrue(state["incomplete"])
            with self.assertRaises(checkpoint.CheckpointError):
                checkpoint.save_baseline(repo / "baseline.json", state)

    def test_symlinked_skill_folder_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "SKILL.md").write_text("secret material", encoding="utf-8")
            base = repo / ".agents/skills"
            base.mkdir(parents=True)
            (base / "elsewhere").symlink_to(outside, target_is_directory=True)
            self.assertEqual(checkpoint.snapshot(repo)["files"], {})

    def test_git_range_detects_only_meaningful_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*parts):
                return subprocess.run(["git", "-C", str(repo), *parts], check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
            git("init", "-q")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Tests")
            (repo / "AGENTS.md").write_text("one", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "initial")
            base = git("rev-parse", "HEAD")
            (repo / "AGENTS.md").write_text("two", encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src/code.py").write_text("pass", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "changed")
            result = checkpoint.evaluate(repo, event="pr", since_ref=base)
            self.assertEqual(result["comparison"], "git-comparison")
            self.assertEqual(result["signals"][0]["paths"], ["AGENTS.md"])
            with self.assertRaises(checkpoint.CheckpointError):
                checkpoint.evaluate(repo, since_ref="--help")


if __name__ == "__main__":
    unittest.main()
