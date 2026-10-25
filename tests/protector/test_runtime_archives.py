"""TAR paths retain POSIX semantics even while a Windows host prepares a guest."""
import io,shutil,sys,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'privacy-assistant'
sys.path.insert(0,str(ROOT/'scripts'))
import local_runtime

class ArchivePaths(unittest.TestCase):
    def archive(self,folder,target):
        path=Path(folder)/'synthetic.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            data=b'fictional library';item=tarfile.TarInfo('runtime/lib/libsample.so.1');item.size=len(data);archive.addfile(item,io.BytesIO(data))
            link=tarfile.TarInfo('runtime/bin/libsample.so');link.type=tarfile.SYMTYPE;link.linkname=target;archive.addfile(link)
        return path
    def test_relative_archive_link_works_on_both_hosts(self):
        with tempfile.TemporaryDirectory() as folder:
            values={name:data for name,data,mode in local_runtime.archive_files(self.archive(folder,'../lib/libsample.so.1'))}
            self.assertEqual(values['runtime/bin/libsample.so'],b'fictional library')
    def test_external_windows_and_missing_targets_rejected(self):
        for target in ('../../../outside','/outside','C:/outside','..\\outside','../lib/missing'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError,'runtime_archive_invalid'):
                    list(local_runtime.archive_files(self.archive(folder,target)))
class GuestBundlePaths(unittest.TestCase):
    def test_guest_library_paths_use_posix_names_on_windows(self):
        import bridge_bundle
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            shutil.copytree(ROOT/'scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            (root/'backend').mkdir()
            for name in ('local-model.json','guest_rpc.py','guest_health.py','acceptance_guest.py','guest_skill.md'):
                shutil.copy2(ROOT/'backend'/name,root/'backend'/name)
            for name in ('skill/scripts/deidentify.py','runtime/Lib/site-packages/pypdf/__init__.py'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'# synthetic fixture')
            values=bridge_bundle.files(root)
            self.assertEqual(values['/opt/privacy-bridge/pypdf/__init__.py'],b'# synthetic fixture')
            self.assertTrue(all('\\' not in name for name in values))

if __name__=='__main__':unittest.main()
