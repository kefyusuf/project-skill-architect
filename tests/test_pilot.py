"""v8 pilot validation: no host observations fabricated, strict metadata only."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pilot  # noqa: E402


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.doc = pilot.create('pilot-a', 'codex', 'project-skill-architect')

    def test_init_fixed_positive_and_negative_cases_all_unobserved(self):
        self.assertGreaterEqual(len(self.doc['cases']), 6)
        self.assertIn('invoke', [c['expected'] for c in self.doc['cases']])
        self.assertIn('skip', [c['expected'] for c in self.doc['cases']])
        self.assertEqual(self.doc['results'], [])
        report = pilot.report(self.doc)
        self.assertEqual(report['evaluation']['status'], 'insufficient_evidence')
        self.assertEqual(report['progress']['candidate']['recorded'], 0)
        self.assertEqual(report['progress']['candidate']['total'], len(self.doc['cases']))
        self.assertEqual(report['progress']['baseline']['recorded'], 0)
        self.assertEqual(report['evaluation']['metrics'][0]['unobserved'], len(self.doc['cases'])*2//2)  # first phase

    def test_record_real_reviewed_result_with_verification(self):
        case = next(c['id'] for c in self.doc['cases'] if c['expected'] == 'invoke')
        pilot.record(self.doc, 'candidate', case, 'invoke', 'pass', 'reviewed_manual', None)
        result = pilot.report(self.doc)
        self.assertEqual(result['progress']['candidate']['recorded'], 1)
        self.assertEqual(result['progress']['candidate']['verified'], 1)
        self.assertEqual(result['evaluation']['status'], 'insufficient_evidence')
        self.assertEqual(result['evaluation']['metrics'][1]['verification_success']['value'], 1.0)

    def test_repeat_record_blocked_and_never_implicitly_overwrites(self):
        case = self.doc['cases'][0]['id']
        pilot.record(self.doc, 'candidate', case, 'invoke', 'unknown', 'reviewed_manual', None)
        with self.assertRaises(pilot.PilotError):
            pilot.record(self.doc, 'candidate', case, 'skip', 'unknown', 'reviewed_manual', None)

    def test_invalid_evidence_or_unverified_tokens_rejected(self):
        case = self.doc['cases'][0]['id']
        with self.assertRaises(pilot.PilotError):
            pilot.record(self.doc, 'candidate', case, 'invoke', 'pass', 'none', None)
        with self.assertRaises(pilot.PilotError):
            pilot.record(self.doc, 'candidate', case, 'invoke', 'pass', 'reviewed_manual', 123)
        with self.assertRaises(pilot.PilotError):
            pilot.record(self.doc, 'candidate', case, 'skip', 'pass', 'reviewed_manual', None)

    def test_skip_case_cannot_be_verified_as_success(self):
        case = next(c['id'] for c in self.doc['cases'] if c['expected'] == 'skip')
        with self.assertRaises(pilot.PilotError):
            pilot.record(self.doc, 'candidate', case, 'skip', 'pass', 'reviewed_manual', None)
        pilot.record(self.doc, 'candidate', case, 'skip', 'unknown', 'reviewed_manual', None)
        self.assertEqual(pilot.report(self.doc)['progress']['candidate']['recorded'], 1)

    def test_missing_and_invalid_diagnostic_fields_rejected(self):
        for replacement in ('../pwn', 'good/slash', 'UPPER'):
            with self.assertRaises(pilot.PilotError):
                pilot.create(replacement, 'codex', 'project-skill-architect')
        other = copy.deepcopy(self.doc)
        other['prompt'] = 'secret'
        with self.assertRaises(pilot.PilotError):
            pilot.validate(other)
        other = copy.deepcopy(self.doc)
        other['cases'].append({'id':'unknown-case','expected':'invoke'})
        with self.assertRaises(pilot.PilotError):
            pilot.validate(other)
        other = copy.deepcopy(self.doc)
        other['results'].append({'phase':'candidate','case_id':self.doc['cases'][0]['id'], 'observed':'skip', 'verification':'unknown', 'evidence':'reviewed_manual','skill_tokens':None,'transcript':'private'})
        with self.assertRaises(pilot.PilotError):
            pilot.validate(other)

    def test_host_isolation_and_baseline_candidate_pairing(self):
        for c in self.doc['cases']:
            v = c['expected']
            verification = 'pass' if v == 'invoke' else 'unknown'
            pilot.record(self.doc, 'baseline', c['id'], v, verification, 'reviewed_manual', None)
            pilot.record(self.doc, 'candidate', c['id'], v, verification, 'reviewed_manual', None)
        result = pilot.report(self.doc)
        self.assertEqual(result['evaluation']['comparison']['matched_pairs'], len(self.doc['cases']))
        self.assertEqual(result['evaluation']['status'], 'no_change')
        self.assertEqual({m['host'] for m in result['evaluation']['metrics']}, {'codex'})

    def test_unknown_outcomes_do_not_count_as_success(self):
        pilot.record(self.doc, 'candidate', self.doc['cases'][0]['id'], 'unknown', 'unknown', 'none', None)
        report = pilot.report(self.doc)
        self.assertEqual(report['progress']['candidate']['recorded'], 0)
        self.assertEqual(report['progress']['candidate']['unknown'], len(self.doc['cases']))
        self.assertEqual(report['evaluation']['status'], 'insufficient_evidence')

    def test_cli_init_record_report_and_safe_overwrite(self):
        script = str(ROOT/'scripts/pilot.py')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'pilot.json'
            init = subprocess.run([sys.executable,script,'init','--file',str(p),'--host','claude'],capture_output=True,text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            original = p.read_bytes()
            again = subprocess.run([sys.executable,script,'init','--file',str(p),'--host','claude'],capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0)
            self.assertEqual(p.read_bytes(),original)
            data = json.loads(original)
            c = data['cases'][0]['id']
            cmd = [sys.executable,script,'record','--file',str(p),'--phase','candidate','--case',c,'--observed','invoke','--verification','pass','--evidence','reviewed_manual']
            rec = subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(rec.returncode,0,rec.stderr)
            final = subprocess.run([sys.executable,script,'report','--file',str(p)],capture_output=True,text=True)
            self.assertEqual(final.returncode,0,final.stderr)
            payload = json.loads(final.stdout)
            self.assertEqual(payload['progress']['candidate']['recorded'],1)
            self.assertEqual(payload['evaluation']['status'],'insufficient_evidence')

    def test_symlink_pilot_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp)/'real.json'
            real.write_text(json.dumps(self.doc),encoding='utf-8')
            link = Path(tmp)/'link.json'
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest('symlinks unavailable')
            with self.assertRaises(pilot.PilotError):
                pilot.read_file(link)


if __name__ == '__main__':
    unittest.main()
