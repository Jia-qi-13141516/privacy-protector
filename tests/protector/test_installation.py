"""Temporary package fixtures, no service registration or host deployment."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'privacy-assistant/protector'))
import install_common as install

class Installation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name).resolve();self.source=self.base/'source';self.source.mkdir()
        (self.source/'entry.py').write_text('synthetic package')
        self.manifest={'version':install.VERSION,'files':{'entry.py':hashlib.sha256((self.source/'entry.py').read_bytes()).hexdigest()}}
        self.save()
    def save(self):
        (self.source/'release.json').write_text(json.dumps(self.manifest));self.digest=hashlib.sha256((self.source/'release.json').read_bytes()).hexdigest()
    def tearDown(self):self.temp.cleanup()
    def test_repeat_copy_preserves_existing_private_state(self):
        parent=self.base/'installed';state=self.base/'private';state.write_bytes(b'FICTIONAL_JOURNAL')
        first=install.copy_verified(self.source,parent,self.digest);second=install.copy_verified(self.source,parent,self.digest)
        self.assertEqual(first,second);self.assertEqual(state.read_bytes(),b'FICTIONAL_JOURNAL');self.assertEqual(len(list(parent.iterdir())),1)
    def test_tampered_package_cannot_create_installed_copy(self):
        (self.source/'entry.py').write_text('tampered')
        with self.assertRaises(ValueError):install.copy_verified(self.source,self.base/'installed',self.digest)
        self.assertFalse((self.base/'installed').exists())
    def test_unlisted_importable_file_is_rejected(self):
        (self.source/'sitecustomize.py').write_text('synthetic')
        with self.assertRaises(ValueError):install.verify_tree(self.source,self.digest)
    def test_conflicting_installed_code_is_preserved_and_rejected(self):
        target=install.copy_verified(self.source,self.base/'installed',self.digest);(target/'entry.py').write_text('other')
        with self.assertRaises(ValueError):install.copy_verified(self.source,self.base/'installed',self.digest)
        self.assertEqual((target/'entry.py').read_text(),'other')
    def test_linked_package_member_cannot_be_copied(self):
        original=self.source/'entry.py';outside=self.base/'outside';original.rename(outside)
        try:original.symlink_to(outside)
        except OSError:self.skipTest('host cannot create symlinks')
        with self.assertRaises(ValueError):install.copy_verified(self.source,self.base/'installed',self.digest)
    def test_case_collisions_and_traversal_rejected(self):
        for name in ('../escape','ENTRY.py','folder\\escape','C:escape'):
            self.manifest['files'][name]='0'*64;self.save()
            with self.assertRaises((ValueError,FileNotFoundError)):install.verify_tree(self.source,self.digest)
            del self.manifest['files'][name]
    def test_development_package_stays_blocked_without_explicit_test_request(self):
        (self.source/'protector').mkdir();(self.source/'protector/qualification.json').write_text('{"release_qualified": false}')
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}):
            with self.assertRaisesRegex(ValueError,'platform_validation_pending'):install.qualification(self.source)
            install.qualification(self.source,test=True)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false','RUNNER_ENVIRONMENT':'local'}):
            with self.assertRaises(ValueError):install.qualification(self.source,test=True)
    def test_package_archive_keeps_mac_runtime_executable(self):
        import zipfile,stat
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
        from package_metadata import member
        archive=self.base/'synthetic.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr(member('runtime/bin/python3',True),b'fictional executable')
            z.writestr(member('protector/service.py'),b'fictional code')
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(stat.S_IMODE(z.getinfo('runtime/bin/python3').external_attr>>16),0o755)
            self.assertEqual(stat.S_IMODE(z.getinfo('protector/service.py').external_attr>>16),0o644)
            self.assertEqual(z.getinfo('runtime/bin/python3').create_system,3)
        if sys.platform=='darwin':
            import subprocess
            subprocess.run(['/usr/bin/unzip','-q',str(archive),'-d',str(self.base/'unzipped')],check=True)
            self.assertTrue(os.access(self.base/'unzipped/runtime/bin/python3',os.X_OK))
    def test_plans_never_use_user_writable_install_roots(self):
        mac=install.install_plan('darwin',501,'arm64');self.assertTrue(mac['app'].startswith('/Library/'));self.assertIn('runtime-macos-arm64',mac['python'])
        with patch.dict(os.environ,{'ProgramData':'C:\\untrusted-agent-directory'}):
            win=install.install_plan('win32','S-1-5-21-999','AMD64');self.assertIn('ProgramData',win['app'])
        with self.assertRaises(ValueError):install.install_plan('win32','sid','arm64')

if __name__=='__main__':unittest.main()
