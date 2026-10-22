"""macOS offline roundtrip and online-child denial using synthetic records."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'privacy-assistant'
sys.path.insert(0, str(ROOT / 'scripts'))
import mac_workflow as workflow
import table_wizard as wizard
import task_channel as ch
from agent_boundary import profile
import openpyxl


@unittest.skipUnless(sys.platform == 'darwin', 'macOS required')
class MacWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='privacy-mac-synthetic-')
        self.base = Path(self.temp.name)
        self.task = self.base / 'Vault' / 'task'
        self.private = self.task / 'private'
        self.private.mkdir(parents=True)
        self.source = self.base / 'original.csv'
        self.rows = [['学号', '姓名', '分数', '备注']] + [
            [f'{i:06}', f'虚构学生{i}', 20 + i % 17, 'PRIVATE_CANARY'] for i in range(60)]
        with self.source.open('w', newline='') as f:
            csv.writer(f).writerows(self.rows)
        ch.put_json(self.private / 'input.json', {'source': str(self.source)})

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        workflow.worker('ingest', self.task)
        ch.put_json(self.private / 'choices.json', ['id', 'drop', 'number', 'drop'])
        workflow.worker('configure', self.task)
        workflow.worker('deidentify', self.task)

    def test_unisolated_worker_reads_nothing(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/mac_worker.py'),
                                 'ingest', str(self.task)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {'status': 'blocked'})
        self.assertFalse((self.private / 'original.csv').exists())
        self.assertNotIn(str(self.source), result.stdout + result.stderr)

    def test_roundtrip_subset_derived_and_original_unchanged(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.prepare()
        release = self.private / 'release'
        for p in release.iterdir():
            text = p.read_text()
            self.assertNotIn('虚构学生', text)
            self.assertNotIn('PRIVATE_CANARY', text)
            self.assertNotIn(str(self.source), text)
        with (release / 'data.csv').open() as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            result = [dict(r, follow_up='yes', priority='2') for r in reader if int(r['measure_3']) >= 30]
        with (self.private / 'returned.csv').open('w', newline='') as f:
            out = csv.DictWriter(f, fieldnames=fields + ['follow_up', 'priority'])
            out.writeheader(); out.writerows(result)
        workflow.worker('preview', self.task)
        workflow.worker('review', self.task)
        self.assertIn('虚构学生', (self.private / 'review.txt').read_text())
        workflow.worker('export', self.task)
        target = self.base / 'Vault/Exports/result.xlsx'
        workflow.export_confirmed(self.task, target)
        book = openpyxl.load_workbook(target)
        actual = list(book.active.values)[1:]; book.close()
        expected = [(r[0], r[1], str(r[2]), '需跟进', 2) for r in self.rows[1:] if r[2] >= 30]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 21)
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).hexdigest())
        with self.assertRaises(ValueError): workflow.export_confirmed(self.task, target)

    def test_child_denies_original_vault_and_worker_changes(self):
        canary = self.private / 'canary'; canary.write_text('LOCAL_ONLY')
        code = self.base / 'App/worker.py'; code.parent.mkdir(); code.write_text('safe')
        exchange = self.base / 'Exchange'; exchange.mkdir()
        script = '''import pathlib,sys,os
for name in sys.argv[1:3]:
 try: pathlib.Path(name).read_bytes()
 except PermissionError: pass
 else: sys.exit(2)
try: pathlib.Path(sys.argv[3]).write_text('changed')
except PermissionError: pass
else: sys.exit(3)
try: os.link(sys.argv[1], str(pathlib.Path(sys.argv[4])/'linked.csv'))
except PermissionError: pass
else: sys.exit(4)
pathlib.Path(sys.argv[4],'result.csv').write_text('person\\np_fake\\n')
'''
        result = subprocess.run(['/usr/bin/sandbox-exec', '-p',
            profile(self.base / 'Vault', protected=[self.source], readonly=[code.parent]),
            sys.executable, '-I', '-B', '-c', script, str(self.source), str(canary), str(code), str(exchange)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(code.read_text(), 'safe')

    def test_tampered_result_does_not_export(self):
        self.prepare()
        with (self.private / 'release/data.csv').open() as f:
            reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
        rows[0]['measure_3'] = '999'
        with (self.private / 'returned.csv').open('w', newline='') as f:
            out = csv.DictWriter(f, fieldnames=fields); out.writeheader(); out.writerows(rows)
        with self.assertRaises(ValueError): workflow.worker('preview', self.task)
        self.assertFalse((self.private / 'reviewed.csv').exists())
        self.assertFalse((self.task / 'export').exists())


if __name__ == '__main__':
    unittest.main()
