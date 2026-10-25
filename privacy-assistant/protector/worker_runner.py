"""Use the existing table/document engines unchanged, inside a separate worker UID.

Linux kernel tests use a network namespace. macOS uses the existing OS network
block. Neither a test-only model nor an alternate task implementation is used.
"""
import hashlib,json,os,shutil,signal,stat,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import posix_store,protocol

def worker_command(root,task,uid,gid):
    if sys.platform=='linux':
        return ['/usr/bin/unshare','--net','--mount','--pid','--fork','--mount-proc',
                sys.executable,'-I','-B',str(Path(__file__).with_name('linux_enter.py')),str(uid),str(gid),str(root),str(task)]
    if sys.platform=='darwin':
        return ['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)(deny mach-lookup)(deny appleevent-send)',
                sys.executable,'-I','-B',str(Path(__file__)),'execute',str(root),str(task)]
    raise ValueError('unsupported_platform')

class Worker:
    def __init__(self,root,work_root,uid,gid,runtime):
        self.root=Path(root);self.work_root=Path(work_root);self.uid=uid;self.gid=gid;self.runtime=runtime
        if os.geteuid()!=0 or uid<=0:raise ValueError('protection_unavailable')
        # Root-owned parent is readable only by the worker group; jobs are 0700.
        s=self.work_root.lstat()
        if s.st_uid!=0 or s.st_gid!=gid or not stat.S_ISDIR(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o750:raise ValueError('private_store_insecure')
    def self_test(self):
        private_job=self.work_root/("selftest-"+uuid.uuid4().hex);private_job.mkdir(mode=0o700)
        try:return self._execute(private_job,None,None)
        finally:shutil.rmtree(private_job,ignore_errors=True)
    def __call__(self,private_job,source,instruction):return self._execute(private_job,source,instruction)
    def _execute(self,private_job,source,instruction):
        task=self.work_root/(private_job.name+'-worker')
        task.mkdir(mode=0o700);os.chown(task,self.uid,self.gid)
        request={'action':'self_test','runtime':self.runtime}
        if source is not None:
            data=source.read_bytes();snapshot=task/source.name;snapshot.write_bytes(data);snapshot.chmod(0o600);os.chown(snapshot,self.uid,self.gid)
            request.update(action='task',source=str(snapshot),instruction=instruction)
        req=task/'worker-request.json';req.write_text(json.dumps(request));req.chmod(0o600);os.chown(req,self.uid,self.gid)
        cmd=worker_command(self.root,task,self.uid,self.gid)
        kwargs={}
        if sys.platform=='darwin':kwargs.update(user=self.uid,group=self.gid,extra_groups=[])
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(task),'TMPDIR':str(task)}
        try:
            p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                env=env,close_fds=True,start_new_session=True,**kwargs)
            try:
                output,_=p.communicate(timeout=3600)
            finally:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait()
            result=json.loads(output)
            if p.returncode:raise ValueError(result.get('code') if result.get('code') in protocol.ERRORS else 'worker_failed')
            if result.get('phase')!='completed':raise ValueError('worker_failed')
            if source is None:return result['self_test']
            if hashlib.sha256(snapshot.read_bytes()).digest()!=hashlib.sha256(data).digest():raise ValueError('source_changed')
            # Import bounded expected artifacts only after the worker has exited.
            names=['result.xlsx'] if result.get('kind')=='table' else ['result.docx','result.txt']
            for name in names:
                fd=posix_store.open_regular(task/name)
                with os.fdopen(fd,'rb') as f:blob=f.read(30*1024*1024+1)
                if len(blob)>30*1024*1024:raise ValueError('worker_failed')
                target=private_job/name;out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(out,'wb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
            posix_store.atomic_json(private_job/'worker-receipt.json',result)
            return result
        finally:
            # No worker child may outlive this task in production. The Linux
            # PID namespace is reaped when its init exits; macOS uses process
            # groups and the fixed inference runner (no arbitrary child code).
            if task.exists():shutil.rmtree(task)

def check_isolation():
    import socket
    for address in [('127.0.0.1',9),('1.1.1.1',443)]:
        sock=socket.socket();sock.settimeout(1)
        try:
            sock.connect(address);raise ValueError('protection_unavailable')
        except PermissionError:pass
        except OSError:
            if sys.platform!='linux' or {p.name for p in Path('/sys/class/net').iterdir()}!={'lo'}:raise ValueError('protection_unavailable')
        finally:sock.close()

def execute(root,task):
    if os.geteuid()==0:raise ValueError('protection_unavailable')
    sys.path.insert(0,str(Path(root)/'scripts'))
    sys.path.insert(0,str(Path(root)/'skill/scripts'))
    sys.path.insert(0,str(Path(root)/'runtime/Lib/site-packages'))
    import task_channel as ch,background_engine as engine,local_runtime
    check_isolation()
    import performance
    performance.require_capacity(performance.hardware(),guest=True)
    request=ch.get_json(Path(task)/'worker-request.json')
    if request['action']=='self_test':
        import self_check
        print(json.dumps({'phase':'completed','self_test':self_check.run_offline(Path(task),request['runtime'],check_isolation)}));return
    source=Path(request['source'])
    model=local_runtime.LocalModel(request['runtime'],Path(task))
    from background_worker import install_execution_guard
    install_execution_guard(str(model.binary))
    result=(engine.table_job if source.suffix in ('.xlsx','.csv') else engine.document_job)(source,Path(task),request['instruction'],model)
    print(json.dumps(dict(result,phase='completed',network='namespace_or_os_denied',worker_uid=os.geteuid(),model_metrics=model.metrics)))

if __name__=='__main__':
    try:execute(sys.argv[2],sys.argv[3])
    except Exception as error:
        print(json.dumps({'phase':'blocked','code':protocol.failure(error)['error']}));sys.exit(2)
