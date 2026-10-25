"""Service entry. Never installs itself; requires root-owned immutable configuration."""
import argparse,json,os,stat,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import protocol

def load_configuration(path):
    import posix_store as permissions
    permissions.root_only();fd=permissions.open_regular(Path(path))
    with os.fdopen(fd,'r') as f:
        st=os.fstat(f.fileno())
        if st.st_uid!=0 or st.st_mode&0o022:raise ValueError('private_store_insecure')
        value=json.load(f)
    expected={'uid','gid','worker_uid','worker_gid','root','store','work','socket_dir','ui','runtime'}
    if set(value)!=expected or any(type(value[k]) is not int or value[k]<=0 for k in ('uid','gid','worker_uid','worker_gid')):raise ValueError('invalid_request')
    if value['uid']==value['worker_uid'] or value['gid']==value['worker_gid']:raise ValueError('protection_unavailable')
    for field in ('root','work','socket_dir'):
        p=Path(value[field])
        for item in [p,*p.parents]:
            s=item.lstat()
            if s.st_uid!=0 or not stat.S_ISDIR(s.st_mode) or s.st_mode&0o022:raise ValueError('private_store_insecure')
    # Python, UI, program files and runtime must not be mutable by the Agent.
    for p in Path(value['root']).rglob('*'):
        s=p.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise ValueError('private_store_insecure')
    # Runtime paths must also be immutable; digest checks alone cannot prevent a swap.
    protected=[Path(sys.executable).resolve(),Path(value['ui'])]
    if value['runtime'] is not None:
        protected.extend([Path(value['runtime']['archive']),Path(value['runtime']['model'])])
        runtime=Path(value['runtime']['runtime']);protected.extend([runtime,*runtime.rglob('*')])
    for p in protected:
        for item in [p,*p.parents]:
            st=item.lstat()
            if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('private_store_insecure')
    return value

def run(configuration):
    if sys.platform not in ('darwin','linux'):raise ValueError('unsupported_platform')
    import posix_store as permissions,unix_rpc
    from broker import Broker
    from worker_runner import Worker
    config=load_configuration(configuration);root=Path(config['root'])
    sys.path.insert(0,str(root/'scripts'));sys.path.insert(0,str(root/'skill/scripts'));sys.path.insert(0,str(root/'runtime/Lib/site-packages'))
    from readiness import Readiness
    import local_runtime,performance
    def prepare(progress):
        runtime=config['runtime']
        if runtime is None:
            runtime=local_runtime.install(Path(config['work'])/'Model',progress=progress)
            # Public components contain no personal data; worker gets read/execute only.
            for item in [Path(config['work'])/'Model',*(Path(config['work'])/'Model').rglob('*')]:
                os.chown(item,0,config['worker_gid']);item.chmod(0o750 if item.is_dir() or item.stat().st_mode&0o111 else 0o640)
            config['runtime']=runtime;permissions.atomic_json(Path(configuration),config)
        local_runtime.verify(runtime)
        load_configuration(configuration)
        return Worker(root,config['work'],config['worker_uid'],config['worker_gid'],runtime)
    def capacity():performance.require_capacity(performance.hardware(),guest=sys.platform=='linux')
    def access_probe():
        probe=Path(config['store'])/'startup-canary'
        if not probe.exists():probe.write_bytes(b'fictional startup probe');probe.chmod(0o600)
        if not permissions.denied_as_user(probe,config['uid'],config['gid']):raise ValueError('permission_probe_failed')
    readiness=Readiness(root,Path(config['store'])/'readiness.json',permissions,prepare,capacity,access_probe)
    ui_path=Path(config['ui']);st=ui_path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('ui_unavailable')
    def ui(mode,identifier):
        protocol.identifier(identifier)
        # The UI runs as the service identity; its private IPC cannot be reused
        # by a same-user Agent. No secret is placed in arguments or user files.
        args=[str(ui_path),mode,identifier,str(Path(config['socket_dir'])/'private.sock')]
        if sys.platform=='darwin':args=['/bin/launchctl','asuser',str(config['uid']),*args]
        else:args=[sys.executable,'-I','-B',*args]
        subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         close_fds=True,start_new_session=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    broker=Broker(config['store'],readiness,ui,config['uid'],config['gid'],permissions,readiness)
    private=threading.Thread(target=unix_rpc.serve,args=(Path(config['socket_dir'])/'private.sock',broker.private,True),daemon=True);private.start()
    readiness.start()
    unix_rpc.serve(Path(config['socket_dir'])/'public.sock',broker.public)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args()
    try:run(a.config)
    except Exception as error:
        print(json.dumps({'phase':'blocked','code':protocol.failure(error)['error']}),file=sys.stderr);sys.exit(2)
