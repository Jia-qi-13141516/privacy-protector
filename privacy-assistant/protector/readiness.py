"""Service-owned readiness. No business file is accepted before real self-test success."""
import hashlib,json,threading,time,traceback,uuid
from pathlib import Path
import protocol

class Readiness:
    def __init__(self,root,state,permissions,prepare,capacity,probe):
        self.root=Path(root);self.state=Path(state);self.permissions=permissions
        self.prepare=prepare;self.capacity=capacity;self.probe=probe
        self.worker=None;self.lock=threading.RLock();self.record={'ready':False,'phase':'preparing','self_test_passed':False}
        self.thread=None;self.last_attempt=0
    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():return
            self.last_attempt=time.monotonic()
            self.record={'ready':False,'phase':'preparing','self_test_passed':False}
            self.thread=threading.Thread(target=self._start,daemon=True);self.thread.start()
    def refresh(self):
        # A later health request can retry temporary resource/download failures.
        # It cannot waive a check or open a business file while retrying.
        retry={'available_memory_low','component_download_failed','component_timeout'}
        with self.lock:
            if self.record.get('phase')=='blocked' and self.record.get('code') in retry and time.monotonic()-self.last_attempt>=30:
                self.start()
        return self.public()
    def public(self):
        with self.lock:return dict(self.record)
    def progress(self,stage,*unused):
        allowed={'preparing','downloading_runtime','downloading_model','self_testing','verifying_access'}
        with self.lock:self.record.update(phase=stage if stage in allowed else 'preparing')
    def key(self):
        import performance,local_runtime
        digest=hashlib.sha256()
        for folder in ('protector','scripts','backend'):
            for p in sorted((self.root/folder).rglob('*')):
                if p.is_file() and p.suffix in ('.py','.swift','.ps1','.json') and '__pycache__' not in p.parts:
                    digest.update(str(p.relative_to(self.root)).encode());digest.update(p.read_bytes())
        digest.update(json.dumps(performance.PROFILE,sort_keys=True).encode())
        digest.update(json.dumps(local_runtime.lock(),sort_keys=True).encode())
        return digest.hexdigest()
    def _start(self):
        try:
            import self_check
            self.capacity();self.worker=self.prepare(self.progress)
            self.progress('verifying_access');self.probe()
            key=self.key();receipt=self.permissions.get_json(self.state) if self.state.exists() else None
            reused=self_check.cache_valid(receipt,key)
            if not reused:
                self.progress('self_testing')
                receipt=self.worker.self_test()
                receipt.update(phase='ready',fingerprint=key)
                if not self_check.cache_valid(receipt,key):raise ValueError('self_test_failed')
                self.permissions.atomic_json(self.state,receipt)
            self.state.with_name('readiness-error.json').unlink(missing_ok=True)
            with self.lock:self.record={'ready':True,'phase':'ready','self_test_passed':True,'self_test_reused':reused,'boundary':'separate_os_identity','material_api':False}
        except Exception as error:
            # Private structural diagnostics only: no exception text, source
            # lines, local variables, request data or absolute paths.
            try:
                frames=[{'module':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)[-8:]]
                self.permissions.atomic_json(self.state.with_name('readiness-error.json'),{'code':protocol.failure(error)['error'],'type':type(error).__name__,'frames':frames})
            except Exception:pass
            with self.lock:self.record={'ready':False,'phase':'blocked','self_test_passed':False,'code':protocol.failure(error)['error']}
    def require(self):
        if not self.public().get('ready'):raise ValueError('not_ready')
        # Available memory changes between tasks; a previous self-test is insufficient.
        self.capacity()
    def __call__(self,*args):
        self.require();return self.worker(*args)
