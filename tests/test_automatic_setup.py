"""No real documents/accounts: control flow, persistence, and hostile requests."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'privacy-assistant'
sys.path.insert(0,str(ROOT/'scripts'))
import auto_setup as setup
import task_channel as ch


class Setup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)/'app'
        self.home=Path(self.temp.name)/'skills'
    def tearDown(self):self.temp.cleanup()
    def install(self):return setup.run('codex',False,self.base,self.home,install_only=True)
    def test_default_install_never_opens_teacher_workflow(self):
        with patch.object(setup.subprocess,'Popen') as process,patch.object(setup.assistant,'start') as start:
            result=setup.run('codex',base=self.base,skill_home=self.home)
        start.assert_not_called()
        self.assertFalse((self.base/'Settings/show-window.json').exists())
        self.assertTrue((self.home/'privacy-assistant/SKILL.md').exists())
        self.assertEqual(result['status'],'background_installation_started')
        self.assertIn('background.py',process.call_args.args[0][2])
        self.assertIn('setup',process.call_args.args[0])
    def test_repeat_install_preserves_profile_bytes(self):
        self.base.mkdir();account=self.base/'existing-client-profile';account.write_bytes(b'FAKE_LOCAL_LOGIN_STATE')
        with patch.object(setup,'probe',return_value={'status':'cli_boundary_verified'}):
            first=self.install();second=self.install()
        self.assertFalse(first['installation_reused']);self.assertTrue(second['installation_reused'])
        self.assertEqual(account.read_bytes(),b'FAKE_LOCAL_LOGIN_STATE')
        self.assertNotIn('FAKE_LOCAL_LOGIN_STATE',(self.base/'Settings/automatic-setup.json').read_text())
        self.assertFalse(second['release_qualified'])
    def test_previous_receipt_never_skips_live_probe(self):
        self.base.mkdir();(self.base/'Settings').mkdir()
        ch.put_json(self.base/'Settings/automatic-setup.json',{'version':'0.7.0','agent':'codex','status':'ready','release_qualified':True})
        with patch.object(setup,'probe',return_value={'status':'blocked','code':'isolation_probe_failed'}) as probe,patch.object(setup.assistant,'start') as launch:
            result=setup.run('codex',True,self.base,self.home)
        probe.assert_called_once();launch.assert_not_called()
        self.assertFalse(result['release_qualified']);self.assertEqual(result['status'],'blocked')
    def test_blocked_backend_never_starts_legacy_fallback(self):
        with patch.object(setup,'probe',return_value={'status':'blocked','code':'persistent_windows_backend_pending'}),patch.object(setup.assistant,'start') as launch:
            result=setup.run('workbuddy',True,self.base,self.home)
        launch.assert_not_called();self.assertEqual(result['code'],'persistent_windows_backend_pending')
    def test_windows_cannot_claim_persistence(self):
        with patch.object(setup.sys,'platform','win32'):
            result=setup.probe('workbuddy',ROOT,self.base)
        self.assertEqual(result['status'],'requires_runtime_bootstrap');self.assertFalse(result['persistent_session_verified'])
    def test_gui_not_replaced_by_cli(self):
        self.assertEqual(setup.probe('workbuddy',ROOT,self.base)['code'],'workbuddy_gui_backend_pending')
    def test_launch_failure_not_relabelled_success(self):
        with patch.object(setup,'probe',return_value={'status':'cli_boundary_verified'}),patch.object(setup.assistant,'start',return_value={'status':'blocked','code':'launch_failed'}):
            self.assertEqual(setup.run('codex',True,self.base,self.home)['status'],'blocked')
    def test_linked_journal_rejected_before_install(self):
        self.base.mkdir();(self.base/'Settings').mkdir();other=self.base/'other';other.write_text('{}')
        (self.base/'Settings/automatic-setup.json').symlink_to(other)
        with self.assertRaises(ValueError):self.install()
        self.assertEqual(other.read_text(),'{}');self.assertFalse((self.base/'App').exists())
    def test_real_mac_cli_canary(self):
        if sys.platform!='darwin':self.skipTest('macOS required')
        if setup.assistant.shutil.which('codex') is None:self.skipTest('local Codex CLI required for live probe')
        result=self.install()
        self.assertEqual(result['status'],'cli_boundary_verified')
        self.assertFalse(result['persistent_session_verified'])
        self.assertFalse(result['current_agent_isolated'])


class Channel(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.id='a'*32
    def tearDown(self):self.temp.cleanup()
    def test_command_and_original_path_rejected(self):
        for key in ('command','input_path','script','confirmed'):
            with self.assertRaises(ValueError):ch.validate_request({'version':1,'id':self.id,'action':'new_table',key:'untrusted'})
    def test_traversal_rejected(self):
        for value in ('../outside','a'*31,'A'*32,None):
            with self.assertRaises(ValueError):ch.task_id(value)
    def test_guest_cannot_confirm_identity_restore(self):
        jobs=ch.Jobs(self.root);jobs.create(self.id)
        for event in ('selected','released','result_received'):jobs.advance(self.id,event)
        with self.assertRaises(ValueError):ch.guest_rpc(self.root,{'action':'local_confirmed','id':self.id})
        self.assertEqual(jobs.phase(self.id),'waiting_for_confirmation')
    def test_bad_transition_rejected(self):
        jobs=ch.Jobs(self.root);jobs.create(self.id)
        with self.assertRaises(ValueError):jobs.advance(self.id,'local_confirmed')
    def test_bounded_read(self):
        file=self.root/'data';file.write_bytes(b'0123456789')
        with self.assertRaises(ValueError):ch.read(file,9)
    def test_fifo_cannot_hang_reader(self):
        if not hasattr(os,'mkfifo'):self.skipTest('POSIX only')
        file=self.root/'fifo';os.mkfifo(file)
        with self.assertRaisesRegex(ValueError,'regular_file_required'):ch.read(file)
    def test_symlink_and_hardlink_rejected(self):
        f=self.root/'source';f.write_bytes(b'LOCAL_SYNTHETIC');link=self.root/'link';link.symlink_to(f)
        with self.assertRaises(ValueError):ch.read(link)
        link.unlink();os.link(f,link)
        with self.assertRaises(ValueError):ch.read(link)
    def test_existing_delivery_not_overwritten(self):
        import base64
        req={'action':'deliver','id':self.id,'data':base64.b64encode(b'person,value\np_fake,2\n').decode()}
        ch.guest_rpc(self.root,req)
        with self.assertRaises(ValueError):ch.guest_rpc(self.root,req)


if __name__=='__main__':unittest.main(verbosity=2)
