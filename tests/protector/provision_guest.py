"""Only for a newly created disposable Linux VM. Never an end-user installer."""
import sys,os,json,subprocess,shutil
from pathlib import Path
assert sys.platform=='linux' and os.geteuid()==0
marker=Path('/etc/privacy-protector-disposable-test')
assert marker.is_file() and marker.stat().st_uid==0 and marker.read_text().strip()=='fictional-materials-only'
assert not Path('/opt/privacy-protector').exists()
subprocess.run(['apt-get','install','-y','libgomp1'],check=True)
for name,uid in [('pp-agent',2001),('pp-worker',2002)]:
 subprocess.run(['useradd','--create-home','--uid',str(uid),'--shell','/usr/sbin/nologin',name],check=True)
root=Path('/opt/privacy-protector')
root.mkdir()
subprocess.run(['tar','-xf','/tmp/protector-code.tar','--strip-components=1','-C',str(root),'privacy-assistant'],check=True)
(root/'tests').mkdir();subprocess.run(['tar','-xf','/tmp/protector-code.tar','--strip-components=2','-C',str(root/'tests'),'tests/protector'],check=True)
base=Path('/opt/privacy-model');cache=base/'Cache';cache.mkdir(parents=True)
spec=json.loads((root/'backend/local-model.json').read_text());asset=spec['runtimes']['linux-aarch64'];model=spec['model']
shutil.move('/tmp/model.gguf',cache/(model['sha256']+'.gguf'))
shutil.move('/tmp/llama-b11856-bin-ubuntu-arm64.tar.gz',cache/(asset['sha256']+'.gz'))
sys.path[:0]=[str(root/'scripts'),str(root/'runtime/Lib/site-packages')]
import local_runtime
runtime=local_runtime.install(base,platform_key='linux-aarch64');local_runtime.verify(runtime)
for directory in (root,base):
 for p in [directory,*directory.rglob('*')]:
  os.chown(p,0,0);p.chmod(0o755 if p.is_dir() or p.stat().st_mode&0o111 else 0o644)
store=Path('/var/lib/privacy-protector-test');store.mkdir(mode=0o700);(store/'jobs').mkdir(mode=0o700)
work=Path('/var/lib/privacy-protector-test-work');work.mkdir(mode=0o750);os.chown(work,0,2002)
socket=Path('/run/privacy-protector-test');socket.mkdir(mode=0o755)
ui=root/'test_ui.py';ui.write_text('# Test only: headless private UI events are driven by the test harness.\n');ui.chmod(0o644)
config={'uid':2001,'gid':2001,'worker_uid':2002,'worker_gid':2002,'root':str(root),'store':str(store/'jobs'),'work':str(work),'socket_dir':str(socket),'ui':str(ui),'runtime':runtime}
p=Path('/etc/privacy-protector-test.json');p.write_text(json.dumps(config));p.chmod(0o600)
print('Temporary guest setup complete; no host deployment.')
