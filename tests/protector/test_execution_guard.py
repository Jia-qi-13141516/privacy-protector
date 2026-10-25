"""Verify the real audit hook in disposable child processes (no global test hook)."""
import json,subprocess,sys,unittest
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[2]/'privacy-assistant/scripts'
class ExecutionGuard(unittest.TestCase):
 @unittest.skipIf(sys.platform=='win32','POSIX spawn probe')
 def test_fixed_spawn_allowed_and_other_executable_blocked(self):
  code='''import sys,os,json,subprocess
sys.path.insert(0,sys.argv[1])
from background_worker import install_execution_guard
install_execution_guard(sys.executable)
allowed=subprocess.run([sys.executable,'-c','pass']).returncode==0
blocked=0
for launch in (lambda:subprocess.run(['/bin/sh','-c','true']),lambda:os.posix_spawn('/bin/sh',['/bin/sh','-c','true'],{}),lambda:os.system('true')):
 try:launch()
 except ValueError:blocked+=1
if hasattr(os,'posix_spawn'):
 pid=os.posix_spawn(sys.executable,[sys.executable,'-c','pass'],{});os.waitpid(pid,0)
print(json.dumps([allowed,blocked]))'''
  r=subprocess.run([sys.executable,'-I','-B','-c',code,str(SCRIPTS)],capture_output=True,text=True,check=True)
  self.assertEqual(json.loads(r.stdout),[True,3])
