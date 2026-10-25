"""SYSTEM-owned originals and private files; no same-user chmod substitute."""
import hashlib,json,os,tempfile
from pathlib import Path
from windows_native import *
USER_TOKEN=None

def user_token(uid):
    token=USER_TOKEN(uid) if USER_TOKEN else active_token(uid)
    if token_sid(token)!=uid:token.Close();raise ValueError('forbidden')
    return token

def secure_dir(path,create=False):
    root_only();p=local_path(path)
    if create:p.mkdir(mode=0o700,exist_ok=True);protect(p)
    for ancestor in (p,*p.parents):
        attrs=win32file.GetFileAttributes(str(ancestor))
        if attrs&win32con.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('private_store_insecure')
    sd=win32security.GetNamedSecurityInfo(str(p),win32security.SE_FILE_OBJECT,SEC)
    if not p.is_dir() or not private_descriptor(sd):raise ValueError('private_store_insecure')
    return p

def assert_private_file(path):
    with anchored(path,win32con.READ_CONTROL) as (h,info):
        if not private_descriptor(descriptor(h)):raise ValueError('private_store_insecure')
def atomic_json(path,value):
    p=Path(path);secure_dir(p.parent);fd,tmp=tempfile.mkstemp(prefix='.journal-',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        protect(tmp);os.replace(tmp,p);assert_private_file(p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def get_json(path):
    assert_private_file(path)
    with anchored(path) as (h,info):return json.loads(win32file.ReadFile(h,1024*1024)[1].decode('utf-8'))
def owner_id(path):
    with anchored(path,win32con.READ_CONTROL) as (h,_):
        sid=owner(descriptor(h));return 0 if sid==SYSTEM else sid

def file_identity(path):
    with anchored(path,win32con.FILE_READ_ATTRIBUTES) as (h,info):return identity(info)

def denied_as_user(path,uid,gid=None):
    root_only();token=user_token(uid)
    try:
        with impersonate(token):
            for access in (win32con.GENERIC_READ,win32con.WRITE_DAC,win32con.WRITE_OWNER):
                try:
                    h=win32file.CreateFile(str(path),access,7,None,win32con.OPEN_EXISTING,win32con.FILE_FLAG_OPEN_REPARSE_POINT,None);h.Close();return False
                except pywintypes.error as error:
                    if error.winerror!=5:return False
        return True
    finally:token.Close()

def seal(source,job,uid,gid,max_bytes,previous=None):
    root_only();source=local_path(source);job=secure_dir(job)
    access=win32con.GENERIC_READ|win32con.READ_CONTROL|win32con.WRITE_DAC|win32con.WRITE_OWNER
    privilege(win32security.SE_TAKE_OWNERSHIP_NAME);privilege(win32security.SE_RESTORE_NAME)
    with anchored(source,access,exclusive=True) as (handle,info):
        # Exclusive open fails on a pre-existing reader, before reading any byte.
        sd=descriptor(handle);owner_sid=owner(sd);dev,ino=identity(info)
        if previous:
            if owner_sid!=SYSTEM or previous.get('stage')!='verified' or previous['uid']!=uid or (previous['dev'],previous['ino'])!=(dev,ino):raise ValueError('source_not_owned')
        elif owner_sid!=uid:raise ValueError('source_not_owned')
        size=(info[5]<<32)|info[6]
        if size>max_bytes:raise ValueError('source_too_large')
        sddl=previous['sddl'] if previous else win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(sd,win32security.SDDL_REVISION_1,SEC)
        record={'source':str(source),'dev':dev,'ino':ino,'uid':uid,'gid':None,'sddl':sddl,'stage':'claiming','size':size}
        atomic_json(job/'source-journal.json',record)
        win32security.SetSecurityInfo(handle,win32security.SE_FILE_OBJECT,win32security.OWNER_SECURITY_INFORMATION|win32security.DACL_SECURITY_INFORMATION|win32security.PROTECTED_DACL_SECURITY_INFORMATION,win32security.ConvertStringSidToSid(SYSTEM),None,system_acl(),None)
        if not private_descriptor(descriptor(handle)):raise ValueError('permission_probe_failed')
        record['stage']='sealed';atomic_json(job/'source-journal.json',record)
    # Sharing violations are never counted as permission denial. The second
    # handle permits sharing; denial must come from the SYSTEM-only descriptor.
    with anchored(source,win32con.GENERIC_READ|win32con.READ_CONTROL) as (handle,after):
        if identity(after)!=(dev,ino) or not private_descriptor(descriptor(handle)):raise ValueError('source_changed')
        if not denied_as_user(source,uid):raise ValueError('permission_probe_failed')
        data=win32file.ReadFile(handle,max_bytes+1)[1]
        if len(data)!=size:raise ValueError('source_changed')
        digest=hashlib.sha256(data).hexdigest()
        if previous and digest!=previous['sha256']:raise ValueError('source_changed')
        snapshot=job/('original'+source.suffix.lower())
        with snapshot.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        assert_private_file(snapshot)
        record.update(stage='verified',sha256=digest,snapshot=snapshot.name);atomic_json(job/'source-journal.json',record)
        return snapshot

def restore(job,uid,gid=None):
    root_only();record=get_json(Path(job)/'source-journal.json')
    if record['uid']!=uid:raise ValueError('forbidden')
    privilege(win32security.SE_RESTORE_NAME)
    with anchored(record['source'],win32con.WRITE_DAC|win32con.WRITE_OWNER|win32con.READ_CONTROL) as (h,info):
        if identity(info)!=(record['dev'],record['ino']):raise ValueError('source_changed')
        sd=win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(record['sddl'],1)
        flag=win32security.PROTECTED_DACL_SECURITY_INFORMATION if sd.GetSecurityDescriptorControl()[0]&win32security.SE_DACL_PROTECTED else win32security.UNPROTECTED_DACL_SECURITY_INFORMATION
        win32security.SetSecurityInfo(h,win32security.SE_FILE_OBJECT,SEC|flag,sd.GetSecurityDescriptorOwner(),sd.GetSecurityDescriptorGroup(),sd.GetSecurityDescriptorDacl(),None)
    record['stage']='released_by_user';atomic_json(Path(job)/'source-journal.json',record)

def export_file(source,destination,uid,gid=None):
    root_only();source=Path(source);dest=local_path(destination)
    if source.suffix.lower()!=dest.suffix.lower():raise ValueError('export_target_invalid')
    assert_private_file(source)
    with anchored(source) as (h,_):data=win32file.ReadFile(h,30*1024*1024+1)[1]
    if len(data)>30*1024*1024:raise ValueError('export_target_invalid')
    token=user_token(uid);parents=[]
    try:
        with impersonate(token):
            for parent in reversed(dest.parents):
                h=win32file.CreateFile(str(parent),win32con.FILE_READ_ATTRIBUTES,3,None,win32con.OPEN_EXISTING,win32con.FILE_FLAG_BACKUP_SEMANTICS|win32con.FILE_FLAG_OPEN_REPARSE_POINT,None);parents.append(h)
                if win32file.GetFileInformationByHandle(h)[0]&win32con.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('export_target_invalid')
            out=win32file.CreateFile(str(dest),win32con.GENERIC_WRITE,0,None,win32con.CREATE_NEW,win32con.FILE_ATTRIBUTE_NORMAL,None)
            try:win32file.WriteFile(out,data);win32file.FlushFileBuffers(out)
            finally:out.Close()
    except Exception:raise ValueError('export_target_invalid') from None
    finally:
        for h in reversed(parents):h.Close()
        token.Close()
