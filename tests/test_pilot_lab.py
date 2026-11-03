"""v8.1 reproducible, synthetic pilot fixture gates."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pilot_lab


@unittest.skipUnless(shutil.which('git'), 'Git required for fixture history')
class PilotLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixtures = self.root / 'fixtures'
        pilot_lab.prepare(self.fixtures)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_case_contract_and_no_agent_observation(self):
        info = pilot_lab.verify(self.fixtures)
        self.assertEqual(info['fixture_count'], 8)
        self.assertEqual(info['observed_agent_sessions'], 0)
        meta = json.loads((self.fixtures / 'pilot-lab.json').read_text())
        self.assertEqual(sum(x['expected'] == 'invoke' for x in meta['cases'].values()), 5)
        self.assertEqual(sum(x['expected'] == 'skip' for x in meta['cases'].values()), 3)

    def test_avoid_duplicate_prompt_requires_evidence_without_prejudging_coverage(self):
        prompt = pilot_lab.CASES['avoid-duplicate'][1]
        self.assertEqual(prompt, (
            'Our team wants an Agent Skill to support release readiness. '
            'Examine the existing project rules, skills, and repository evidence. '
            'Decide whether a new skill is justified, an existing skill should be revised, '
            'or no change is necessary. Explain the evidence. Do not modify files.'
        ))
        self.assertEqual(pilot_lab.CASES['avoid-duplicate'][0], 'invoke')
        self.assertNotIn('already covers', prompt.lower())

    def test_v84_fixture_schema_does_not_accept_prior_suite_manifest(self):
        self.assertEqual(pilot_lab.SCHEMA, 2)
        legacy = self.fixtures / 'pilot-lab.json'
        payload = json.loads(legacy.read_text(encoding='utf-8'))
        payload['schema_version'] = 1
        legacy.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.verify(self.fixtures)

    def test_git_history_for_code_only_change_and_workflow_change(self):
        for case in ('review-noop', 'evolve-meaningful'):
            out = subprocess.check_output(['git', '-C', str(self.fixtures / case), 'rev-list', '--count', 'HEAD'], text=True)
            self.assertEqual(out.strip(), '2')
        changed = subprocess.check_output(['git', '-C', str(self.fixtures / 'review-noop'), 'diff', 'HEAD~1', 'HEAD', '--name-only'], text=True)
        self.assertEqual(changed.strip(), 'src/calculator.py')
        changed2 = subprocess.check_output(['git', '-C', str(self.fixtures / 'evolve-meaningful'), 'diff', 'HEAD~1', 'HEAD', '--name-only'], text=True)
        self.assertIn('.github/workflows/release.yml', changed2)

    def test_suite_is_synthetic_and_cases_do_not_contain_real_secrets(self):
        for case in pilot_lab.CASES:
            repo = self.fixtures / case
            self.assertTrue((repo / '.git').is_dir())
            self.assertTrue((repo / 'README.md').exists())
        self.assertFalse((self.fixtures / 'bootstrap-project' / 'AGENTS.md').exists())
        self.assertTrue((self.fixtures / 'adopt-existing' / '.agents/skills/release-check/SKILL.md').exists())

    def test_stage_is_copy_only_and_does_not_mutate_template(self):
        target = self.root / 'candidate-adopt'
        outcome = pilot_lab.stage(self.fixtures, 'adopt-existing', target)
        self.assertEqual(outcome['observed_agent_sessions'], 0)
        (target / 'AGENTS.md').write_text('changed')
        self.assertEqual(pilot_lab.verify(self.fixtures)['status'], 'ready')
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.stage(self.fixtures, 'adopt-existing', target)

    def test_modified_fixture_refused(self):
        (self.fixtures / 'bootstrap-project' / 'README.md').write_text('modified')
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.verify(self.fixtures)
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.stage(self.fixtures, 'bootstrap-project', self.root / 'new')

    def test_unexpected_manifest_value_refused(self):
        meta_file = self.fixtures / 'pilot-lab.json'
        meta = json.loads(meta_file.read_text())
        meta['cases']['bootstrap-project']['expected'] = 'skip'
        meta_file.write_text(json.dumps(meta))
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.verify(self.fixtures)

    def test_preflight_does_not_claim_activation(self):
        outcome = pilot_lab.preflight(self.fixtures / 'adopt-existing', 'codex')
        self.assertFalse(outcome['activation_verified'])
        self.assertFalse(outcome['skill_file_present'])
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.preflight(self.fixtures / 'adopt-existing', 'other')

    def test_existing_destinations_never_overwritten(self):
        with self.assertRaises(pilot_lab.LabError):
            pilot_lab.prepare(self.fixtures)
        self.assertEqual(pilot_lab.verify(self.fixtures)['status'], 'ready')

    def test_cli_end_to_end_without_claiming_real_host(self):
        runner = ROOT / 'scripts/pilot_lab.py'
        res = subprocess.run([sys.executable, str(runner), 'stage', '--fixtures', str(self.fixtures),
                              '--case', 'unrelated-bugfix', '--dest', str(self.root / 'bugfix')],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        info = json.loads(res.stdout)
        self.assertEqual(info['expected'], 'skip')
        check = subprocess.run([sys.executable, str(runner), 'preflight', '--repo', str(self.root / 'bugfix'),
                                '--host', 'claude'], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertFalse(json.loads(check.stdout)['activation_verified'])

    def test_fixture_digests_deterministic_across_prepares(self):
        second = self.root / 'second'
        pilot_lab.prepare(second)
        first_m = json.loads((self.fixtures / 'pilot-lab.json').read_text())
        second_m = json.loads((second / 'pilot-lab.json').read_text())
        self.assertEqual(first_m, second_m)


if __name__ == '__main__':
    unittest.main()
