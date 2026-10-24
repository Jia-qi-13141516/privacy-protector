"""Small, bounded file protocol. No original-file paths or executable requests."""
import base64,json,os,re,stat,sys,tempfile,time,uuid
from pathlib import Path
MAX_BYTES=20*1024*1024
ID=re.compile(r'^[a-f0-9]{32}$')
PHASES={'waiting_for_file','processing_local','ready_for_agent','waiting_for_confirmation','completed','cancelled','blocked'}


def task_id(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('invalid_task')
    return value


def regular(path):
    for p in (path,*path.absolute().parents):
        if str(p) not in ('/tmp','/var') and (p.is_symlink() or getattr(p,'is_junction',lambda:False)()):raise ValueError('linked_path')
    if path.exists() and path.is_file() and path.stat().st_nlink!=1:raise ValueError('linked_file')


def read(path,limit=MAX_BYTES):
    regular(path)
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)|getattr(os,'O_NONBLOCK',0)
    if sys.platform=='linux':
        # Anchor every parent with openat, preventing symlink-swap races.
        parts=path.absolute().parts
        if '..' in parts:raise ValueError('linked_path')
        directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in parts[1:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                os.close(directory);directory=child
            fd=os.open(parts[-1],flags,dir_fd=directory)
        finally:os.close(directory)
    else:fd=os.open(path,flags)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode):raise ValueError('regular_file_required')
        if s.st_nlink!=1:raise ValueError('linked_file')
        data=f.read(limit+1)
    if len(data)>limit:raise ValueError('too_large')
    return data


def write(path,data,exclusive=False):
    regular(path);path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive and path.exists():raise ValueError('already_exists')
    fd,tmp=tempfile.mkstemp(prefix='.part-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        if exclusive:
            os.link(tmp,path);os.unlink(tmp)
        else:os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def put_json(path,obj,exclusive=False):write(path,json.dumps(obj,ensure_ascii=False).encode(),exclusive)
def get_json(path,limit=32768):return json.loads(read(path,limit))


def validate_request(obj):
    if not isinstance(obj,dict) or set(obj)!={'version','id','action'}:raise ValueError('invalid_request')
    if obj['version']!=1 or obj['action'] not in ('new_table','new_document','submit_result'):raise ValueError('invalid_request')
    task_id(obj['id']);return obj


def decode_blob(value):
    if not isinstance(value,str) or len(value)>MAX_BYTES*4//3+8:raise ValueError('too_large')
    data=base64.b64decode(value,validate=True)
    if len(data)>MAX_BYTES:raise ValueError('too_large')
    return data


def guest_rpc(root,request):
    """Called by a fixed SSH forced-command; treats the guest queue as untrusted."""
    regular(root)
    if not isinstance(request,dict):raise ValueError('invalid_request')
    action=request.get('action')
    if action=='poll' and set(request)=={'action'}:
        for path in sorted(root.glob('request-*.json')):
            obj=validate_request(get_json(path));identifier=task_id(obj['id'])
            if path.name!='request-'+identifier+'.json':raise ValueError('invalid_request')
            return {'request':obj}
        return {'request':None}
    if action=='ack' and set(request)=={'action','id'}:
        identifier=task_id(request['id']);path=root/('request-'+identifier+'.json');regular(path);path.unlink(missing_ok=True);return {'ok':True}
    identifier=task_id(request.get('id'));folder=root/identifier;regular(folder)
    if action=='deliver' and set(request) in ({'action','id','data'},{'action','id','data','columns'}):
        if 'columns' in request:
            columns=request['columns'];meanings={'身份代号','数值','分类','分数','得分','总分','年龄','年级','性别','学院','班级','人数','次数','时长','完成情况'}
            if not isinstance(columns,list) or not 1<=len(columns)<=200:raise ValueError('invalid_columns')
            for c in columns:
                if not isinstance(c,dict) or set(c)!={'output','kind','meaning'} or c['kind'] not in ('id','number','category') or c['meaning'] not in meanings or not isinstance(c['output'],str) or not re.fullmatch(r'(person|measure_[0-9]{1,3}|category_[0-9]{1,3})',c['output']):raise ValueError('invalid_columns')
            put_json(folder/'columns.json',columns,exclusive=True)
        write(folder/'data.csv',decode_blob(request['data']),exclusive=True)
        put_json(folder/'status.json',{'phase':'ready_for_agent'});return {'ok':True}
    if action=='deliver_document' and set(request)=={'action','id','data'}:
        data=decode_blob(request['data'])
        if len(data)>1024*1024:raise ValueError('too_large')
        data.decode('utf-8')
        write(folder/'document.txt',data,exclusive=True)
        put_json(folder/'status.json',{'phase':'ready_for_agent','kind':'document'})
        return {'ok':True}
    if action=='document_result' and set(request)=={'action','id'}:
        return {'data':base64.b64encode(read(folder/'result.txt',1024*1024)).decode()}
    if action=='result' and set(request)=={'action','id'}:
        return {'data':base64.b64encode(read(folder/'result.csv')).decode()}
    if action=='status' and set(request)=={'action','id','phase'} and request['phase'] in PHASES:
        put_json(folder/'status.json',{'phase':request['phase']});return {'ok':True}
    raise ValueError('invalid_request')


class Jobs:
    """Host-only state. The guest cannot approve a result or supply local paths."""
    def __init__(self,root):self.root=Path(root);regular(self.root);self.root.mkdir(parents=True,exist_ok=True)
    def path(self,identifier):return self.root/(task_id(identifier)+'.json')
    def create(self,identifier,kind='table'):
        if kind not in ('table','document'):raise ValueError('kind_invalid')
        put_json(self.path(identifier),{'phase':'waiting_for_file','kind':kind},exclusive=True)
    def kind(self,identifier):return get_json(self.path(identifier)).get('kind','table')
    def phase(self,identifier):return get_json(self.path(identifier))['phase']
    def advance(self,identifier,event):
        old=self.phase(identifier)
        transitions={('waiting_for_file','selected'):'processing_local',('processing_local','released'):'ready_for_agent',
                     ('ready_for_agent','result_received'):'waiting_for_confirmation',('waiting_for_confirmation','local_confirmed'):'completed'}
        if event in ('cancel','block') and old not in ('completed','cancelled','blocked'):new='cancelled' if event=='cancel' else 'blocked'
        elif (old,event) in transitions:new=transitions[old,event]
        else:raise ValueError('invalid_transition')
        put_json(self.path(identifier),{'phase':new,'kind':self.kind(identifier)});return new
