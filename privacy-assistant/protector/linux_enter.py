"""Fixed Linux namespace setup for integration tests; executes no material code as root."""
import os,subprocess,sys
from pathlib import Path
if os.geteuid()!=0 or len(sys.argv)!=5:sys.exit(2)
uid,gid=int(sys.argv[1]),int(sys.argv[2])
if uid<=0 or gid<=0:sys.exit(2)
subprocess.run(['/usr/bin/mount','-t','sysfs','sysfs','/sys'],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
args=['/usr/bin/setpriv','--reuid',str(uid),'--regid',str(gid),'--clear-groups','--no-new-privs','--bounding-set=-all',sys.executable,'-I','-B',str(Path(__file__).with_name('worker_runner.py')),'execute',sys.argv[3],sys.argv[4]]
os.execv(args[0],args)
