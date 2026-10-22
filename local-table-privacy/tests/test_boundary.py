import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from agent_boundary import profile,paths
from windows_agent import configuration,stage_bundle
from windows_host import stage_selected
import xml.etree.ElementTree as ET

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name).resolve();self.vault=self.d/'vault';self.ex=self.d/'exchange';self.vault.mkdir();self.ex.mkdir()
        self.raw=self.vault/'synthetic.txt';self.raw.write_text('SYNTHETIC_ONLY')
    def tearDown(self):self.tmp.cleanup()
    def run_isolated(self,source,*args):
        r=subprocess.run(['/usr/bin/sandbox-exec','-p',profile(self.vault),sys.executable,'-I','-c',source,*map(str,args)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout.strip()
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_direct_read_and_write(self):
        self.assertEqual(self.run_isolated("import pathlib,sys\np=pathlib.Path(sys.argv[1])\nfor op in [lambda:p.read_bytes(),lambda:p.write_bytes(b'x')]:\n try:op()\n except PermissionError:pass\n else:sys.exit(3)\nprint('denied')",self.raw),'denied')
        self.assertEqual(self.raw.read_text(),'SYNTHETIC_ONLY')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_child_shell_cannot_escape(self):
        self.assertEqual(self.run_isolated("import subprocess,sys\nr=subprocess.run(['/bin/cat',sys.argv[1]],capture_output=True)\nassert r.returncode!=0 and b'SYNTHETIC_ONLY' not in r.stdout\nprint('denied')",self.raw),'denied')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_symlink_read_denied(self):
        link=self.ex/'alias';link.symlink_to(self.raw)
        self.assertEqual(self.run_isolated("import pathlib,sys\ntry:pathlib.Path(sys.argv[1]).read_bytes()\nexcept PermissionError:print('denied')\nelse:sys.exit(3)",link),'denied')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_hardlink_creation_denied(self):
        self.assertEqual(self.run_isolated("import os,sys\ntry:os.link(sys.argv[1],sys.argv[2])\nexcept PermissionError:print('denied')\nelse:sys.exit(3)",self.raw,self.ex/'hard'),'denied')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_exchange_writable(self):
        self.run_isolated("import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('ok')",self.ex/'answer.txt');self.assertEqual((self.ex/'answer.txt').read_text(),'ok')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_loopback_bridge_denied_host_unchanged(self):
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.listen()
            self.assertEqual(self.run_isolated("import socket,sys\ns=socket.socket()\ntry:s.connect(('127.0.0.1',int(sys.argv[1])))\nexcept PermissionError:print('denied')\nelse:sys.exit(3)",s.getsockname()[1]),'denied')
            with socket.create_connection(s.getsockname(),1):conn,_=s.accept();conn.close()
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_nested_sandbox_cannot_relax(self):
        self.run_isolated("import subprocess,sys\nr=subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)','/bin/cat',sys.argv[1]],capture_output=True)\nassert r.returncode!=0 and b'SYNTHETIC_ONLY' not in r.stdout",self.raw)
    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):paths(self.vault,self.vault)
    def test_windows_agent_only_exchange_writable(self):
        x=ET.fromstring(configuration(self.ex,self.d/'bundle'))
        maps=x.findall('MappedFolders/MappedFolder');self.assertEqual(len(maps),2)
        self.assertEqual([m.findtext('SandboxFolder') for m in maps if m.findtext('ReadOnly')=='false'],[r'C:\Exchange'])
        self.assertNotIn(str(self.vault),ET.tostring(x,encoding='unicode'));self.assertEqual(x.findtext('Networking'),'Enable')
        self.assertEqual(x.findtext('ClipboardRedirection'),'Disable')
    def test_selected_file_stages_no_neighbors(self):
        (self.vault/'unrelated.txt').write_text('DO_NOT_COPY')
        dest=self.d/'stage';stage_selected(self.raw,dest)
        self.assertEqual([p.name for p in dest.iterdir()],['synthetic.txt']);self.assertEqual((dest/'synthetic.txt').read_bytes(),self.raw.read_bytes())
    def test_staging_symlink_rejected(self):
        p=self.ex/'alias';p.symlink_to(self.raw)
        with self.assertRaises(Exception):stage_selected(p,self.d/'stage')


class ReleaseBoundaryTests(unittest.TestCase):
    def test_existing_hardlink_preflight_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);v=d/'v';e=d/'e';v.mkdir();e.mkdir();(v/'raw').write_text('fake');(e/'alias').hardlink_to(v/'raw')
            with self.assertRaises(ValueError):paths(v,e)
    def test_bundle_does_not_copy_user_added_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);skill=d/'skill';skill.mkdir();(skill/'SKILL.md').write_text('fake skill');(skill/'secret.xlsx').write_text('do not copy')
            import hashlib
            (skill/'package_manifest.json').write_text(json.dumps({'SKILL.md':hashlib.sha256(b'fake skill').hexdigest()}))
            stage_bundle(d/'bundle',skill)
            self.assertFalse((d/'bundle/local-table-privacy/secret.xlsx').exists())
            self.assertEqual((d/'bundle/local-table-privacy/SKILL.md').read_text(),'fake skill')
    def test_modified_distribution_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);skill=d/'skill';skill.mkdir();(skill/'SKILL.md').write_text('modified')
            (skill/'package_manifest.json').write_text(json.dumps({'SKILL.md':'0'*64}))
            with self.assertRaises(ValueError):stage_bundle(d/'bundle',skill)

    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_unicode_path_full_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);v=d/'原表保护区';e=d/'可用材料';v.mkdir();e.mkdir()
            r=subprocess.run([sys.executable,str(ROOT/'scripts/agent_boundary.py'),'--vault',str(v),'--exchange',str(e),'--check'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout);self.assertEqual(json.loads(r.stdout)['status'],'boundary_probe_passed')
    @unittest.skipUnless(sys.platform=='darwin','macOS boundary')
    def test_generic_unix_bridge_stays_denied(self):
        import socket
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp).resolve();v=d/'vault';v.mkdir();p=d/'bridge.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(p));server.listen()
                code="import socket,sys\ns=socket.socket(socket.AF_UNIX)\ntry:s.connect(sys.argv[1])\nexcept PermissionError:print('denied')\nelse:sys.exit(3)"
                r=subprocess.run(['/usr/bin/sandbox-exec','-p',profile(v),sys.executable,'-I','-c',code,str(p)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'denied')

if __name__=='__main__':unittest.main()
