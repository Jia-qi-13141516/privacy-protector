"""Fixed guest code payload. No user data, profile or credentials in this bundle."""
import base64,hashlib,io,json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED


def files(root):
    result={}
    for name in ('task_channel.py','guest_client.py','table_wizard.py','network_policy.py','document_engine.py',
                 'local_runtime.py','component_download.py','background_engine.py','background_worker.py','performance.py','self_check.py'):
        result['/opt/privacy-bridge/'+name]=(root/'scripts'/name).read_bytes()
    result['/opt/privacy-bridge/local-model.json']=(root/'backend/local-model.json').read_bytes()
    for name in ('guest_rpc.py','guest_health.py','acceptance_guest.py','guest_skill.md'):
        result['/opt/privacy-bridge/'+name]=(root/'backend'/name).read_bytes()
    result['/opt/skill/scripts/deidentify.py']=(root/'skill/scripts/deidentify.py').read_bytes()
    library=root/'runtime/Lib/site-packages'
    for path in sorted((library/'pypdf').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
            result['/opt/privacy-bridge/'+path.relative_to(library).as_posix()]=path.read_bytes()
    for path in library.glob('pypdf-*.dist-info/licenses/LICENSE'):
        result['/opt/privacy-bridge/vendor-licenses/pypdf-LICENSE']=path.read_bytes()
    if not any('/pypdf/' in key for key in result):raise ValueError('pdf_runtime_missing')
    return result


def payload(root):
    values=files(root);out=io.BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for path,data in sorted(values.items()):z.writestr(path.lstrip('/'),data)
    return out.getvalue()


# Runs only as root via the host's private Guest Control channel. It cannot see
# incoming Agent commands; package contents were verified by the host installer.
APPLY = r'''
import hashlib,os,pathlib,sys,zipfile
source=pathlib.Path(sys.argv[1]);expected=sys.argv[2]
if os.geteuid()!=0 or source.parent!=pathlib.Path('/var/lib/privacy-install'):raise RuntimeError('update_path')
if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise RuntimeError('update_hash')
with zipfile.ZipFile(source) as z:
 infos=z.infolist()
 if len(infos)>500 or sum(x.file_size for x in infos)>15000000:raise RuntimeError('update_size')
 for entry in infos:
  n=entry.filename;p=pathlib.PurePosixPath(n)
  if p.is_absolute() or '..' in p.parts or '\\' in n or not (n.startswith('opt/privacy-bridge/') or n=='opt/skill/scripts/deidentify.py'):raise RuntimeError('update_file')
 for entry in infos:
  dest=pathlib.Path('/')/entry.filename
  if any(p.is_symlink() for p in (dest,*dest.parents)):raise RuntimeError('update_link')
  dest.parent.mkdir(parents=True,exist_ok=True)
  temporary=dest.with_name(dest.name+'.new')
  fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
  with os.fdopen(fd,'wb') as stream:stream.write(z.read(entry))
  os.replace(temporary,dest)
role=__import__('json').loads(pathlib.Path('/etc/privacy-assistant-guest.json').read_text())['role']
if role=='online':
 import pwd
 pid=os.fork()
 if pid==0:
  try:
   user=pwd.getpwnam('teacher');os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
   import tempfile
   content=pathlib.Path('/opt/privacy-bridge/guest_skill.md').read_bytes()
   for home in ('.workbuddy','.codebuddy','.agents','.claude'):
    dest=pathlib.Path('/home/teacher')/home/'skills/privacy-assistant/SKILL.md'
    if any(p.is_symlink() for p in (dest,*dest.parents)):raise RuntimeError('update_link')
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.privacy-update-',dir=dest.parent)
    try:
     with os.fdopen(fd,'wb') as stream:stream.write(content)
     os.replace(tmp,dest)
    finally:
     if os.path.exists(tmp):os.unlink(tmp)
  except Exception:os._exit(2)
  os._exit(0)
 if os.waitpid(pid,0)[1]!=0:raise RuntimeError('profile_skill_update_failed')
source.unlink()
print('updated')
'''


def update(backend, root, roles=('offline','online')):
    from task_channel import write
    data=payload(root);digest=hashlib.sha256(data).hexdigest()
    for role in roles:
        entry=backend.state['machines'][role]
        if entry.get('bridge_sha256')==digest:continue
        backend.start(role)
        local=backend.base/'Settings'/('bridge-'+role+'.zip')
        write(local,data)
        remote='/var/lib/privacy-install/bridge-update.zip'
        try:
            backend.cli('guestcontrol',entry['id'],'copyto',*backend.credentials(role),str(local),remote)
            reply=backend.guest(role,'/usr/bin/python3',['-I','-c',APPLY,remote,digest])
            if reply.strip()!='updated':raise ValueError('bridge_update_failed')
            if backend.rpc(role,{'action':'health'}).get('status')!=role:raise ValueError('boundary_changed')
            entry['bridge_sha256']=digest;backend.save()
        finally:local.unlink(missing_ok=True)
