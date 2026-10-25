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
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name).resolve();self.app=self.base/'app'
        (self.app/'skills/start').mkdir(parents=True);(self.app/'skills/start/SKILL.md').write_text('synthetic skill')
    def tearDown(self):self.temp.cleanup()
    def test_plan_never_installs_or_contacts_service(self):
        b=setup.bootstrap
        with patch.object(b,'identity',return_value=501),patch.object(b.sys,'platform','darwin'),patch.object(b.platform,'machine',return_value='arm64'),patch.object(b.subprocess,'run') as process,patch.object(b.client,'request') as rpc:
            result=b.run('codex',True)
        self.assertFalse(result['installed']);process.assert_not_called();rpc.assert_not_called()
    def test_unqualified_build_stops_before_system_authorization(self):
        b=setup.bootstrap
        with patch.object(b,'identity',return_value=501),patch.object(b.sys,'platform','darwin'),patch.object(b.platform,'machine',return_value='arm64'),patch.object(b.subprocess,'run') as process,patch.object(b.client,'request') as rpc:
            with self.assertRaisesRegex(ValueError,'platform_validation_pending'):b.run('codex')
        process.assert_not_called();rpc.assert_not_called()
    def test_existing_service_reuses_login_and_never_reinstalls(self):
        b=setup.bootstrap;login=self.base/'fake-login';login.write_bytes(b'FICTIONAL_LOGIN')
        with patch.object(b,'identity',return_value=501),patch.object(b.sys,'platform','darwin'),patch.object(b.platform,'machine',return_value='arm64'),patch.object(b,'qualification'),patch.object(b,'verify_tree'),patch.object(b.client,'request',return_value={'ready':False,'phase':'self_testing'}),patch.object(b.subprocess,'run') as process,patch.object(b,'install_launcher'):
            result=b.run('codex')
        process.assert_not_called();self.assertTrue(result['installation_reused']);self.assertFalse(result['ready']);self.assertFalse(result['account_files_modified']);self.assertEqual(login.read_bytes(),b'FICTIONAL_LOGIN')
    def test_custom_skill_never_overwritten(self):
        b=setup.bootstrap;dest=self.base/'.agents/skills/privacy-protector';dest.mkdir(parents=True);(dest/'SKILL.md').write_text('teacher-owned')
        with patch.object(b.Path,'home',return_value=self.base):
            with self.assertRaisesRegex(ValueError,'existing_skill_preserved'):b.install_launcher('codex',self.app)
        self.assertEqual((dest/'SKILL.md').read_text(),'teacher-owned')
    def test_managed_skill_repeat_install_is_idempotent(self):
        b=setup.bootstrap
        with patch.object(b.Path,'home',return_value=self.base):
            b.install_launcher('workbuddy',self.app);first=(self.base/'.codebuddy/skills/privacy-protector/SKILL.md').read_bytes();b.install_launcher('workbuddy',self.app)
        self.assertEqual((self.base/'.codebuddy/skills/privacy-protector/SKILL.md').read_bytes(),first)
    def test_unknown_agent_does_not_install(self):
        with self.assertRaisesRegex(ValueError,'agent_invalid'):setup.run('unsupported')


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
