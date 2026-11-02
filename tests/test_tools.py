import importlib.util
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_inspector = load("project_inspector")
distribute = load("distribute")
validate = load("validate")


class SkillArchitectureTests(unittest.TestCase):
    def test_standard_library_inspect_is_not_shadowed_from_script_directory(self):
        # Direct script execution puts scripts/ first on sys.path.
        completed = subprocess.run(
            [sys.executable, "-S", "-c", "import inspect; assert callable(inspect.get_annotations)"],
            cwd=ROOT / "scripts", capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_standalone_pilot_host_entrypoint_is_importable(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/pilot_host.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_baseline_skill_is_valid(self):
        self.assertEqual(validate.check(ROOT), [])

    def test_validator_accepts_dot_from_skill_root(self):
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate.py"), "."],
                                   cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_adopt_inspects_existing_project_without_writes(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch)
            (repo / "AGENTS.md").write_text("Existing rules", encoding="utf-8")
            path = repo / ".claude/skills/ship"
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("---\nname: ship\ndescription: Release\n---\nDo work", encoding="utf-8")
            before = set(repo.rglob("*"))
            summary = project_inspector.inspect(repo)
            self.assertEqual(summary["instructions"], ["AGENTS.md"])
            self.assertEqual(summary["skill_roots"][".claude/skills"][0]["name"], "ship")
            self.assertEqual(set(repo.rglob("*")), before)

    def test_default_plan_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch)
            plan = distribute.plan(ROOT, repo, "common,claude")
            self.assertEqual([status for _, status, _ in plan], ["CREATE", "CREATE"])
            self.assertFalse((repo / ".agents").exists())
            self.assertFalse((repo / ".claude").exists())

    def test_distributor_refuses_unmanaged_conflicts(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch)
            destination = repo / ".claude/skills/project-skill-architect"
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("other project", encoding="utf-8")
            plan = distribute.plan(ROOT, repo, "common,claude")
            self.assertEqual([status for _, status, _ in plan], ["CREATE", "BLOCK"])

    def test_staging_modes_preserve_platform_security_contract(self):
        self.assertEqual(distribute._staging_mode("win32"), 0o777)
        self.assertEqual(distribute._staging_mode("linux"), 0o700)
        self.assertEqual(distribute._staging_mode("darwin"), 0o700)

    @unittest.skipUnless(sys.platform == "win32", "Windows ACL inheritance check")
    def test_windows_installation_inherits_parent_acl(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "repo" / ".agents" / "skills" / "project-skill-architect"
            files = distribute.source_files(ROOT)
            distribute.install(ROOT, target, files, distribute.fingerprints(files))
            script = "(Get-Acl -LiteralPath '" + str(target).replace("'", "''") + "').AreAccessRulesProtected"
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip().lower(), "false",
                             "Installed skill directory must inherit the parent's ACL")

    def test_managed_copy_detects_local_changes_and_repeated_sync(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch)
            files = distribute.source_files(ROOT)
            hashes = distribute.fingerprints(files)
            dest = repo / ".claude/skills/project-skill-architect"
            distribute.install(ROOT, dest, files, hashes)
            self.assertEqual(distribute.target_state(dest, hashes)[0], "UNCHANGED")
            (dest / "SKILL.md").write_text("modified", encoding="utf-8")
            self.assertEqual(distribute.target_state(dest, hashes)[0], "BLOCK")

    def test_managed_copy_can_sync_authorized_canonical_update(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch)
            canonical = repo / ".agents/skills/sample-skill"
            canonical.mkdir(parents=True)
            skill = canonical / "SKILL.md"
            skill.write_text("---\nname: sample-skill\ndescription: Demo\n---\nOriginal", encoding="utf-8")
            dest = repo / ".claude/skills/sample-skill"
            files = distribute.source_files(canonical)
            original = distribute.fingerprints(files)
            distribute.install(canonical, dest, files, original)
            skill.write_text("---\nname: sample-skill\ndescription: Demo\n---\nRevised", encoding="utf-8")
            updated = distribute.fingerprints(distribute.source_files(canonical))
            self.assertEqual(distribute.target_state(dest, updated)[0], "UPDATE")
            distribute.install(canonical, dest, distribute.source_files(canonical), updated)
            self.assertEqual(distribute.target_state(dest, updated)[0], "UNCHANGED")
            self.assertIn("Revised", (dest / "SKILL.md").read_text(encoding="utf-8"))

    def test_distributor_blocks_symlinked_installation_root(self):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch) / "repo"
            outside = Path(scratch) / "outside"
            repo.mkdir()
            outside.mkdir()
            (repo / ".claude").symlink_to(outside, target_is_directory=True)
            plan = distribute.plan(ROOT, repo, "claude")
            self.assertEqual(plan[0][1], "BLOCK")
            self.assertEqual(list(outside.iterdir()), [])

    def test_source_with_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "example"
            root.mkdir()
            (root / "SKILL.md").write_text("---\nname: example\ndescription: X\n---\nX", encoding="utf-8")
            (root / "sub").symlink_to(root, target_is_directory=True)
            with self.assertRaises(distribute.DistributionError):
                distribute.source_files(root)


if __name__ == "__main__":
    unittest.main()
