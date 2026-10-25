"""Resource safety, automatic readiness, and queue behaviour. Real model tests run separately."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]/'privacy-assistant'
sys.path.insert(0, str(ROOT/'scripts'))
import performance as p
import background as bg
import self_check
import task_channel as ch


class Resources(unittest.TestCase):
    def info(self, total=8, available=3, platform='darwin'):
        return {'total_bytes': int(total*p.GIB), 'available_bytes': int(available*p.GIB), 'cores': 4, 'platform': platform}
    def test_eight_gb_with_headroom_accepted(self):
        p.require_capacity(self.info())
    def test_four_gb_rejected_even_if_free(self):
        with self.assertRaisesRegex(ValueError, 'memory_below_requirement'): p.require_capacity(self.info(4,3))
    def test_busy_sixteen_gb_not_accepted_by_total_alone(self):
        with self.assertRaisesRegex(ValueError, 'available_memory_low'): p.require_capacity(self.info(16,1))
    def test_windows_reserves_vm_without_double_counting(self):
        with self.assertRaisesRegex(ValueError, 'available_memory_low'): p.require_capacity(self.info(8,3,'win32'))
        p.require_capacity(self.info(8,4,'win32'))
        p.require_capacity(self.info(8,1,'win32'),vm_running=True)
    def test_running_vm_still_reserves_host_memory(self):
        with self.assertRaisesRegex(ValueError,'available_memory_low'):p.require_capacity(self.info(8,.25,'win32'),vm_running=True)
    def test_guest_capacity_does_not_require_eight_gb_inside_vm(self):
        p.require_capacity(self.info(3,2,'linux'),guest=True)
        with self.assertRaisesRegex(ValueError,'available_memory_low'):p.require_capacity(self.info(3,1,'linux'),guest=True)
    def test_mac_does_not_count_swap_or_compressed_pages_as_free(self):
        text='Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 10.\nPages inactive: 20.\nPages speculative: 5.\nPages occupied by compressor: 999999.\nSwapins: 999999.\n'
        self.assertEqual(p.mac_available(text),35*16384)
    def test_unknown_memory_not_silently_zero_or_unlimited(self):
        with self.assertRaisesRegex(ValueError,'resource_probe_failed'):p.mac_available('invalid')
    def test_real_rss_probe(self):
        if sys.platform not in ('darwin','linux'):self.skipTest('offline worker platform')
        self.assertGreater(p.resident_bytes(os.getpid()),0)
    def test_table_worker_has_its_own_memory_guard(self):
        with patch.object(p,'resident_bytes',return_value=3*p.GIB),self.assertRaisesRegex(ValueError,'worker_memory_limit'):
            p.guard_worker(12345)


class Monitor(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def child(self):
        return [sys.executable,'-B','-c','import time;time.sleep(5)']
    def test_over_budget_process_is_killed(self):
        if sys.platform not in ('darwin','linux'):self.skipTest('offline worker platform')
        start=time.monotonic()
        with patch.dict(p.PROFILE,{'max_rss_bytes':1}),self.assertRaisesRegex(ValueError,'inference_memory_limit'):
            p.inference(self.child(),self.root/'out',self.root/'err')
        self.assertLess(time.monotonic()-start,2)
    def test_slow_process_is_killed(self):
        if sys.platform not in ('darwin','linux'):self.skipTest('offline worker platform')
        start=time.monotonic()
        with patch.dict(p.PROFILE,{'timeout_seconds':.1}),self.assertRaisesRegex(ValueError,'inference_timeout'):
            p.inference(self.child(),self.root/'out',self.root/'err')
        self.assertLess(time.monotonic()-start,2)
    def test_missing_monitor_never_runs_unobserved(self):
        start=time.monotonic()
        with patch.object(p,'resident_bytes',return_value=None),self.assertRaisesRegex(ValueError,'memory_monitor_unavailable'):
            p.inference(self.child(),self.root/'out',self.root/'err')
        self.assertLess(time.monotonic()-start,2)
    def test_success_has_actual_measurement(self):
        if sys.platform not in ('darwin','linux'):self.skipTest('offline worker platform')
        result=p.inference([sys.executable,'-B','-c','import time;print("synthetic");time.sleep(.15)'],self.root/'out',self.root/'err')
        self.assertGreater(result['peak_rss_bytes'],0);self.assertGreater(result['elapsed_seconds'],.1)


class Readiness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        (self.base/'Settings').mkdir();(self.base/'Vault').mkdir()
    def tearDown(self):self.temp.cleanup()
    def valid(self):
        return dict(phase='ready',fingerprint='expected',profile='compact',local_model_calls=2,
                    peak_rss_bytes=p.GIB,elapsed_seconds=10,checks=dict.fromkeys(self_check.CHECKS,True))
    def test_old_ready_receipt_is_not_performance_acceptance(self):
        self.assertFalse(self_check.cache_valid({'phase':'ready','version':'0.9.0'},'expected'))
    def test_changed_runtime_requires_new_check(self):
        self.assertFalse(self_check.cache_valid(self.valid(),'new-fingerprint'))
    def test_incorrect_or_missing_trial_checks_block_reuse(self):
        for name in self_check.CHECKS:
            receipt=self.valid();receipt['checks'][name]=False
            self.assertFalse(self_check.cache_valid(receipt,'expected'))
    def test_no_real_model_call_cannot_pass(self):
        receipt=self.valid();receipt['local_model_calls']=0
        self.assertFalse(self_check.cache_valid(receipt,'expected'))
    def test_excess_time_or_memory_cannot_pass(self):
        for key,value in [('elapsed_seconds',181),('peak_rss_bytes',3*p.GIB)]:
            receipt=self.valid();receipt[key]=value
            self.assertFalse(self_check.cache_valid(receipt,'expected'))
    def test_self_test_failure_precedes_business_file_read(self):
        identifier='a'*32;task=self.base/'Vault/Background'/identifier;task.mkdir(parents=True)
        missing=self.base/'must-not-be-read.xlsx'
        ch.put_json(task/'request.json',{'source':str(missing),'instruction':'统计记录数'})
        with patch.object(bg,'ensure_ready',side_effect=ValueError('self_test_result_mismatch')),patch.object(bg,'run_mac_worker') as worker:
            bg.run(self.base,identifier)
        worker.assert_not_called();self.assertFalse(any(task.glob('original.*')))
        status=bg.state(self.base,identifier)
        self.assertEqual(status['code'],'self_test_result_mismatch');self.assertIn('虚构材料',status['message'])
    def test_memory_block_is_clear_and_never_calls_worker(self):
        identifier='b'*32;task=self.base/'Vault/Background'/identifier;task.mkdir(parents=True)
        ch.put_json(task/'request.json',{'source':'PRIVATE_CANARY','instruction':'统计记录数'})
        with patch.object(bg,'ensure_ready',side_effect=ValueError('available_memory_low')),patch.object(bg,'run_mac_worker') as worker:
            bg.run(self.base,identifier)
        worker.assert_not_called();status=bg.state(self.base,identifier)
        self.assertIn('可用内存不足',status['message']);self.assertNotIn('PRIVATE_CANARY',json.dumps(status))
    def test_setup_failure_cannot_leave_stale_ready(self):
        ch.put_json(self.base/'Settings/background-setup.json',{'phase':'ready'})
        with patch.object(bg,'ensure_ready',side_effect=ValueError('isolation_failed')):bg.setup(self.base)
        status=ch.get_json(self.base/'Settings/background-setup.json')
        self.assertEqual(status['phase'],'blocked');self.assertIn('断网保护',status['message'])
    def test_runtime_lock_serializes_processes(self):
        first=self.base/'first';second=self.base/'second'
        code='import sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from background import runtime_lock;root=Path(sys.argv[2]);marker=Path(sys.argv[3]);\nwith runtime_lock(root):\n marker.write_text(str(time.monotonic()));time.sleep(float(sys.argv[4]))\n'
        a=subprocess.Popen([sys.executable,'-B','-c',code,str(ROOT/'scripts'),str(self.base),str(first),'.4'])
        try:
            deadline=time.monotonic()+5
            while not first.exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(first.exists())
            b=subprocess.Popen([sys.executable,'-B','-c',code,str(ROOT/'scripts'),str(self.base),str(second),'0'])
            try:
                b.wait(timeout=5);a.wait(timeout=5)
                self.assertGreaterEqual(float(second.read_text())-float(first.read_text()),.35)
            finally:
                if b.poll() is None:b.kill();b.wait()
        finally:
            if a.poll() is None:a.kill();a.wait()


class WindowsControl(unittest.TestCase):
    def test_guest_memory_checked_before_source_bytes(self):
        import background_windows as win
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);backend=Mock();backend.rpc.side_effect=ValueError('available_memory_low')
            info={'total_bytes':8*p.GIB,'available_bytes':p.GIB,'platform':'win32','cores':4}
            with patch.object(p,'hardware',return_value=info),patch('windows_service.safe_source') as read:
                with self.assertRaisesRegex(ValueError,'available_memory_low'):
                    win.execute(base,base/'task',{'source':'PRIVATE_CANARY.xlsx','instruction':'统计记录数'},lambda *args:None,backend)
                read.assert_not_called()
        self.assertEqual(backend.rpc.call_args.args,('offline',{'action':'resource_health'}))


if __name__=='__main__':unittest.main()
