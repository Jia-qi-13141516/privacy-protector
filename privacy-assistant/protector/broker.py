"""Protected controller. Public RPC never accepts paths or returns material content."""
import csv,io,json,os,queue,stat,threading,uuid
from pathlib import Path
import protocol

class Broker:
    def __init__(self,store,worker,ui,uid,gid,permissions,readiness):
        self.readiness=readiness
        self.store=Path(store);self.uid=uid;self.gid=gid;self.permissions=permissions
        permissions.secure_dir(self.store)
        self.worker=worker;self.ui=ui;self.lock=threading.RLock();self.pending=queue.Queue()
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
        # Never resume processing a half-sealed source after a crash. The private
        # journal enables human recovery; the Agent cannot unseal or export it.
        for p in self.store.iterdir():
            if p.is_dir() and protocol.ID.fullmatch(p.name) and (p/'job.json').is_file():
                r=self._load(p.name)
                if r['phase'] in ('sealing','queued','processing'):
                    r.update(phase='blocked',code='source_changed');self._save(r)
    def _path(self,identifier):return self.store/protocol.identifier(identifier)
    def _load(self,identifier):
        try:return self.permissions.get_json(self._path(identifier)/'job.json')
        except FileNotFoundError:raise ValueError('task_missing') from None
    def _save(self,record):self.permissions.atomic_json(self._path(record['id'])/'job.json',record)
    def public(self,obj,peer):
        if peer!=self.uid:raise ValueError('forbidden')
        protocol.public_request(obj)
        with self.lock:
            if obj['action']=='health':return self.readiness.refresh()
            if obj['action']=='submit':
                self.readiness.require()
                identifier=uuid.uuid4().hex;p=self._path(identifier);p.mkdir(mode=0o700)
                r={'id':identifier,'phase':'waiting_for_file','task':obj['task'],'sealed':False};self._save(r)
                try:self.ui('select',identifier)
                except Exception:
                    r.update(phase='blocked',code='ui_unavailable');self._save(r)
                return protocol.status(r)
            r=self._load(obj['id'])
            if obj['action']=='review':
                if r['phase'] not in ('waiting_for_confirmation','blocked','confirmed','cancelled'):raise ValueError('invalid_transition')
                self.ui('review',r['id'])
            return protocol.status(r)
    def private(self,obj,peer):
        if peer!=0:raise ValueError('forbidden')
        protocol.private_request(obj);identifier=obj['id']
        with self.lock:
            r=self._load(identifier);p=self._path(identifier);action=obj['action']
            if action=='select':
                self.readiness.require()
                if r['phase']!='waiting_for_file':raise ValueError('invalid_transition')
                source=Path(obj['path']);suffix=source.suffix.lower()
                if suffix not in ('.xlsx','.csv','.txt','.md','.docx','.pdf'):raise ValueError('invalid_request')
                r['phase']='sealing';self._save(r)
                try:
                    previous=self._previous_source(source)
                    snapshot=self.permissions.seal(source,p,self.uid,self.gid,20*1024*1024 if suffix in ('.xlsx','.csv') else 5*1024*1024,previous=previous)
                    r.update(phase='queued',sealed=True,snapshot=snapshot.name,kind='table' if suffix in ('.xlsx','.csv') else 'document')
                except Exception as error:
                    journal=p/'source-journal.json'
                    r.update(phase='blocked',code=protocol.failure(error)['error'],sealed=journal.exists() and self.permissions.get_json(journal).get('stage')=='verified')
                    self._save(r);return protocol.status(r)
                self._save(r);self.pending.put(identifier);return protocol.status(r)
            if action=='review':
                journal=p/'source-journal.json';source_extension=''
                if journal.exists():source_extension=Path(self.permissions.get_json(journal)['source']).suffix.lower()
                if r['phase'] in ('blocked','cancelled'):return {'id':identifier,'phase':r['phase'],'code':r.get('code','worker_failed'),'original_stays_protected':r.get('sealed',False),'source_extension':source_extension}
                if r['phase'] not in ('waiting_for_confirmation','confirmed'):return protocol.status(r)
                return {'id':identifier,'phase':r['phase'],'preview':self._preview(p,r),
                        'extension':'.xlsx' if r['kind']=='table' else '.docx','source_extension':source_extension,
                        'notice':'原件继续受保护。确认导出后，普通目录中的结果文件可被其他软件读取。'}
            if action=='confirm':
                if r['phase']!='waiting_for_confirmation':raise ValueError('invalid_transition')
                result=p/('result.xlsx' if r['kind']=='table' else 'result.docx')
                self.permissions.export_file(result,Path(obj['destination']),self.uid,self.gid)
                r['phase']='confirmed';self._save(r);return protocol.status(r)
            if action=='recover':
                if r['phase'] not in ('blocked','confirmed','cancelled'):raise ValueError('invalid_transition')
                record=self.permissions.get_json(p/'source-journal.json')
                if record.get('stage')!='verified' or record['uid']!=self.uid:raise ValueError('invalid_transition')
                snapshot=p/record['snapshot']
                import hashlib
                if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('source_changed')
                self.permissions.export_file(snapshot,Path(obj['destination']),self.uid,self.gid)
                return {'id':identifier,'recovered':True,'notice':'取回的原件副本已成为普通文件。'}
            if action=='restore':
                # Root-only trusted UI operation; release is explicit, never a
                # side effect of task failure, uninstall or a public RPC request.
                if r['phase'] not in ('blocked','confirmed','cancelled'):raise ValueError('invalid_transition')
                record=self.permissions.get_json(p/'source-journal.json');related=self._related_sources(record)
                if any(x['phase'] in ('sealing','queued','processing') for x in related):raise ValueError('source_busy')
                self.permissions.restore(p,self.uid,self.gid)
                for item in related:
                    item.update(sealed=False,original_released_by_user=True);self._save(item)
                return protocol.status(self._load(identifier))
            if action=='cancel':
                if r['phase'] not in ('waiting_for_file','waiting_for_confirmation','blocked'):raise ValueError('invalid_transition')
                r['phase']='cancelled';self._save(r);return protocol.status(r)
    def _related_sources(self,record):
        related=[]
        for p in self.store.iterdir():
            if not protocol.ID.fullmatch(p.name) or not (p/'source-journal.json').is_file():continue
            j=self.permissions.get_json(p/'source-journal.json')
            if (j['dev'],j['ino'])==(record['dev'],record['ino']):related.append(self._load(p.name))
        return related
    def _previous_source(self,source):
        if self.permissions.owner_id(source)!=0:return None
        identity=self.permissions.file_identity(source)
        matches=[]
        for p in self.store.iterdir():
            journal=p/'source-journal.json'
            if not protocol.ID.fullmatch(p.name) or not journal.is_file():continue
            j=self.permissions.get_json(journal)
            if j.get('stage')=='verified' and j.get('uid')==self.uid and (j['dev'],j['ino'])==identity:matches.append((journal.stat().st_mtime_ns,j))
        if matches:return max(matches,key=lambda item:item[0])[1]
        raise ValueError('source_not_owned')
    def _preview(self,p,r):
        if r['kind']=='document':return (p/'result.txt').read_text()[:100000]
        import openpyxl
        book=openpyxl.load_workbook(p/'result.xlsx',read_only=True,data_only=False)
        out=io.StringIO()
        for sheet in book:
            out.write(sheet.title+'\n');writer=csv.writer(out,delimiter='\t')
            for row in sheet.values:writer.writerow(['' if v is None else str(v) for v in row])
            out.write('\n')
        book.close();return out.getvalue()[:100000]
    def _run(self):
        while True:
            identifier=self.pending.get()
            try:
                with self.lock:r=self._load(identifier);r['phase']='processing';self._save(r)
                p=self._path(identifier);reply=self.worker(p,p/r['snapshot'],r['task'])
                # No path supplied by a child process is accepted.
                if reply.get('kind')!=r['kind']:raise ValueError('worker_failed')
                names=['result.xlsx'] if r['kind']=='table' else ['result.docx','result.txt']
                for name in names:
                    self.permissions.assert_private_file(p/name)
                with self.lock:r=self._load(identifier);r['phase']='waiting_for_confirmation';self._save(r)
                try:self.ui('review',identifier)
                except Exception:pass  # Saved result can be reopened through public review.
            except Exception as error:
                with self.lock:
                    r=self._load(identifier);r.update(phase='blocked',code=protocol.failure(error)['error']);self._save(r)
            finally:self.pending.task_done()
