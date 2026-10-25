"""Control-flow tests only; actual kernel/model validation is in the VM harness."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]/'privacy-assistant'
sys.path[:0]=[str(ROOT/'protector'),str(ROOT/'scripts')]
from readiness import Readiness
from broker import Broker
import self_check

class Files:
    @staticmethod
    def secure_dir(path):Path(path).mkdir(exist_ok=True)
    @staticmethod
    def get_json(path):return json.loads(Path(path).read_text())
    @staticmethod
    def atomic_json(path,value):Path(path).write_text(json.dumps(value))

class Ready(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.worker=Mock();self.worker.self_test.return_value={'checks':dict.fromkeys(self_check.CHECKS,True),'profile':'compact','local_model_calls':2,'peak_rss_bytes':10_000_000,'elapsed_seconds':1.5}
        self.capacity=Mock();self.probe=Mock();self.prepare=Mock(return_value=self.worker)
    def tearDown(self):self.temp.cleanup()
    def gate(self):
        gate=Readiness(ROOT,self.base/'receipt.json',Files,self.prepare,self.capacity,self.probe)
        gate.key=lambda:'fictional-test-fingerprint'
        return gate
    def test_ready_requires_access_probe_and_complete_real_check_receipt(self):
        g=self.gate();g._start();self.assertTrue(g.public()['ready'])
        self.probe.assert_called_once();self.worker.self_test.assert_called_once()
        self.assertTrue(self_check.cache_valid(Files.get_json(g.state),g.key()))
    def test_any_failed_check_prevents_readiness_and_receipt(self):
        for check in self_check.CHECKS:
            with self.subTest(check=check):
                receipt=copy.deepcopy(self.worker.self_test.return_value);receipt['checks'][check]=False
                with patch.object(self.worker,'self_test',return_value=receipt):
                    g=self.gate();g._start();self.assertFalse(g.public()['ready']);self.assertFalse(g.state.exists())
    def test_access_failure_never_runs_model_or_creates_receipt(self):
        self.probe.side_effect=ValueError('permission_probe_failed');g=self.gate();g._start()
        self.worker.self_test.assert_not_called();self.assertFalse(g.state.exists());self.assertEqual(g.public()['phase'],'blocked')
    def test_reuse_rechecks_access_and_available_memory(self):
        g=self.gate();g._start();g2=self.gate();g2._start()
        self.assertTrue(g2.public()['self_test_reused']);self.assertEqual(self.probe.call_count,2);self.worker.self_test.assert_called_once()
        self.capacity.side_effect=ValueError('memory_low')
        with self.assertRaises(ValueError):g2.require()
    def test_retry_never_reuses_failed_state_or_skips_selftest(self):
        self.capacity.side_effect=ValueError('available_memory_low');g=self.gate();g._start()
        self.capacity.side_effect=None;g.last_attempt=-100
        g.refresh();g.thread.join(5)
        self.assertTrue(g.public()['ready']);self.worker.self_test.assert_called_once();self.probe.assert_called_once()
    def test_permanent_protection_failure_does_not_spin_or_fallback(self):
        self.probe.side_effect=ValueError('permission_probe_failed');g=self.gate();g._start();g.last_attempt=-100
        with patch.object(g,'start') as start:g.refresh();start.assert_not_called()
        self.assertFalse(g.public()['ready'])
    def test_code_change_invalidates_cached_check(self):
        g=self.gate();g._start();g2=self.gate();g2.key=lambda:'changed';g2._start()
        self.assertFalse(g2.public()['self_test_reused']);self.assertEqual(self.worker.self_test.call_count,2)
    def test_failure_never_copies_exception_material_to_health(self):
        self.prepare.side_effect=RuntimeError('SECRET_STUDENT /private/source.xlsx')
        g=self.gate();g._start();self.assertNotIn('SECRET',json.dumps(g.public()))
    def test_broker_never_opens_picker_before_ready(self):
        g=self.gate();ui=Mock();store=self.base/'jobs';b=Broker(store,self.worker,ui,501,20,Files,g)
        with self.assertRaisesRegex(ValueError,'not_ready'):b.public({'action':'submit','task':'统计记录数'},501)
        self.assertEqual(list(store.iterdir()),[]);ui.assert_not_called();self.worker.assert_not_called()
    def test_capacity_failure_at_selection_never_reads_original(self):
        g=self.gate();g._start();ui=Mock();store=self.base/'jobs';b=Broker(store,self.worker,ui,501,20,Files,g)
        r=b.public({'action':'submit','task':'统计记录数'},501)
        self.capacity.side_effect=ValueError('memory_low')
        with self.assertRaisesRegex(ValueError,'memory_low'):
            b.private({'action':'select','id':r['id'],'path':'/does-not-exist/synthetic.xlsx'},0)
        self.assertEqual(b._load(r['id'])['phase'],'waiting_for_file')
        self.assertFalse(any(store.rglob('original.*')))

if __name__=='__main__':unittest.main()
