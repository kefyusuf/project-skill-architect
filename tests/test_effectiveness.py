"""v7: fail-closed skill effectiveness evaluation. Deterministic fixtures only."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('effectiveness', ROOT / 'scripts/effectiveness.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def case(case_id, *, phase='candidate', expected='invoke', observed='invoke',
         verification='pass', evidence='host_trace', skill='release-review', host='codex',
         skill_tokens=None):
    return {'case_id':case_id, 'phase':phase, 'skill':skill, 'host':host,
            'expected':expected, 'observed':observed, 'verification':verification,
            'evidence':evidence, 'skill_tokens':skill_tokens}


def dataset(*items):
    return {'schema_version':1, 'suite_id':'release-eval', 'runs':list(items)}


class EffectivenessTests(unittest.TestCase):
    def test_unknown_observations_never_count_as_failure_or_success(self):
        data = dataset(case('a', observed='unknown', verification='unknown', evidence='none'))
        result = mod.evaluate(data)
        row = result['metrics'][0]
        self.assertEqual(row['unobserved'],1)
        self.assertIsNone(row['activation_precision']['value'])
        self.assertIsNone(row['activation_recall']['value'])
        self.assertIsNone(row['verification_success']['value'])
        self.assertEqual(result['status'],'insufficient_evidence')

    def test_positive_negative_trigger_and_outcome_counts(self):
        data = dataset(case('tp'), case('fp',expected='skip',verification='unknown'),
                       case('fn',observed='skip',verification='unknown'),
                       case('tn',expected='skip',observed='skip',verification='unknown'),
                       case('fail',verification='fail'))
        row = mod.evaluate(data)['metrics'][0]
        self.assertEqual(row['confusion'],{'tp':2,'fp':1,'fn':1,'tn':1})
        self.assertEqual(row['activation_precision']['value'], 2/3)
        self.assertEqual(row['activation_recall']['value'], 2/3)
        self.assertEqual(row['verification_success']['value'], .5)
        self.assertEqual(mod.evaluate(data)['status'],'review_recommended')

    def test_deduped_keys_prevent_inflated_rates(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('same'),case('same')))

    def test_require_evidence_for_observed_behavior(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',evidence='none')))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',observed='unknown',evidence='host_trace')))

    def test_verification_requires_true_positive_invocation(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',expected='skip',verification='pass')))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',observed='skip',verification='fail')))

    def test_token_measurements_require_host_trace_and_invocation(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',evidence='reviewed_manual',skill_tokens=123)))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',observed='skip',verification='unknown',skill_tokens=123)))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',skill_tokens=-1)))

    def test_report_measured_token_stats_without_token_guesses(self):
        data=dataset(case('a',skill_tokens=120),case('b',skill_tokens=80),case('c'))
        row=mod.evaluate(data)['metrics'][0]
        self.assertEqual(row['skill_tokens'],{'measured_cases':2,'min':80,'max':120,'mean':100})
        self.assertEqual(row['verification_success']['denominator'],3)

    def test_matched_pairs_detect_real_regressions_and_no_automatic_edit(self):
        data=dataset(case('a',phase='baseline'),case('a',phase='candidate',observed='skip',verification='unknown'),
                     case('b',phase='baseline',verification='pass'),case('b',phase='candidate',verification='fail'))
        result=mod.evaluate(data)
        self.assertEqual(result['comparison']['matched_pairs'],2)
        self.assertEqual(result['comparison']['activation_regressions'],['codex/release-review/a'])
        self.assertEqual(result['comparison']['verification_regressions'],['codex/release-review/b'])
        self.assertEqual(result['status'],'review_recommended')
        self.assertEqual(result['action'],'review_existing')
        self.assertFalse('create_skill' in json.dumps(result))

    def test_pairs_not_mixed_across_skill_or_host(self):
        data=dataset(case('a',phase='baseline',host='codex'),case('a',phase='candidate',host='claude'))
        result=mod.evaluate(data)
        self.assertEqual(result['comparison']['matched_pairs'],0)
        self.assertEqual(result['status'],'insufficient_evidence')

    def test_unmatched_and_undetermined_are_not_regressions(self):
        data=dataset(case('a',phase='baseline'),case('a',phase='candidate',observed='unknown',verification='unknown',evidence='none'))
        result=mod.evaluate(data)
        self.assertEqual(result['comparison']['activation_regressions'],[])
        self.assertEqual(result['status'],'insufficient_evidence')

    def test_complete_clean_matched_dataset_is_no_change(self):
        data=dataset(case('a',phase='baseline'),case('a',phase='candidate'),
                     case('b',phase='baseline',expected='skip',observed='skip',verification='unknown'),
                     case('b',phase='candidate',expected='skip',observed='skip',verification='unknown'))
        self.assertEqual(mod.evaluate(data)['status'],'no_change')

    def test_unmatched_candidate_case_blocks_no_change(self):
        data=dataset(case('a',phase='baseline'),case('a',phase='candidate'),
                     case('b',phase='baseline',expected='skip',observed='skip',verification='unknown'),
                     case('b',phase='candidate',expected='skip',observed='skip',verification='unknown'),
                     case('new',observed='unknown',evidence='none',verification='unknown'))
        self.assertEqual(mod.evaluate(data)['status'], 'insufficient_evidence')

    def test_no_negative_scenarios_does_not_prove_trigger_selectivity(self):
        data=dataset(case('a',phase='baseline'),case('a',phase='candidate'))
        self.assertEqual(mod.evaluate(data)['status'], 'insufficient_evidence')

    def test_host_bound_ids_prevent_misleading_collisions(self):
        data=dataset(case('a',phase='baseline',host='codex'),
                     case('a',phase='candidate',host='codex',observed='skip',verification='unknown'),
                     case('a',phase='baseline',host='claude'),
                     case('a',phase='candidate',host='claude',verification='fail'))
        result=mod.evaluate(data)
        self.assertEqual(result['comparison']['activation_regressions'],['codex/release-review/a'])
        self.assertEqual(result['comparison']['verification_regressions'],['claude/release-review/a'])

    def test_inconsistent_expectations_cannot_be_compared(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',phase='baseline'),case('a',phase='candidate',expected='skip',verification='unknown')))

    def test_bounded_schema_no_pii_free_text_fields(self):
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset({**case('a'), 'prompt':'private information'}))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('../secret')))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate(dataset(case('a',host='not-a-host')))
        with self.assertRaises(mod.EffectivenessError):
            mod.evaluate({'schema_version':1,'suite_id':'ok','runs':[case(f'c{i}') for i in range(501)]})

    def test_command_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'eval.json'
            path.write_text(json.dumps(dataset(case('a',observed='unknown',evidence='none',verification='unknown'))))
            before=sorted(str(p.relative_to(root)) for p in Path(root).rglob('*'))
            run=subprocess.run([sys.executable,str(ROOT/'scripts/effectiveness.py'),'evaluate','--suite',str(path)],
                               text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)['status'],'insufficient_evidence')
            self.assertEqual(before,sorted(str(p.relative_to(root)) for p in Path(root).rglob('*')))


if __name__=='__main__':
    unittest.main()
