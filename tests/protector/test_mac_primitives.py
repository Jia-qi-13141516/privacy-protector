"""Unprivileged macOS API checks with disposable invented files, no installation."""
import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'privacy-assistant/protector'))
import posix_store
@unittest.skipUnless(sys.platform=='darwin','macOS only')
class MacPrimitives(unittest.TestCase):
 def test_no_acl_is_valid_and_roundtrip_keeps_file(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as folder:
   p=Path(folder)/'synthetic.txt';p.write_text('fictional data');before=p.read_bytes()
   fd=os.open(p,os.O_RDONLY)
   try:
    posix_store.local_filesystem(fd)
    acl=posix_store._darwin_acl(fd,read_only=True)
    posix_store._darwin_acl(fd);posix_store._darwin_acl(fd,restore=acl)
    self.assertEqual(posix_store._darwin_acl(fd,read_only=True),acl)
   finally:os.close(fd)
   self.assertEqual(p.read_bytes(),before)
