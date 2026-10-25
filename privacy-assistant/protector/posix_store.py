"""Root-owned storage and in-place source sealing; no host setup at import time.

Protection begins after sealing, not before selection. Previously copied/uploaded
bytes cannot be recalled. Root/admin and screen capture are outside this boundary.
"""
import ctypes,errno,hashlib,json,os,stat,subprocess,sys,tempfile
from pathlib import Path


def root_only():
    if os.geteuid()!=0:raise ValueError('protection_unavailable')

def open_regular(path,flags=os.O_RDONLY):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise ValueError('linked_source')
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
        fd=os.open(p.name,flags|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    finally:os.close(directory)
    s=os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
        os.close(fd);raise ValueError('linked_source')
    return fd

def secure_dir(path,create=False):
    root_only();p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise ValueError('private_store_insecure')
    if create:p.mkdir(parents=False,mode=0o700,exist_ok=True)
    s=p.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)&0o077:raise ValueError('private_store_insecure')
    # A protected directory must not be replaceable through an agent-owned ancestor.
    for parent in p.parents:
        st=parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or stat.S_IMODE(st.st_mode)&0o022:raise ValueError('private_store_insecure')
    return p

def atomic_json(path,value):
    p=Path(path);secure_dir(p.parent)
    fd,temp=tempfile.mkstemp(prefix='.journal-',dir=p.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(temp,p)
        d=os.open(p.parent,os.O_RDONLY);os.fsync(d);os.close(d)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def get_json(path):
    fd=open_regular(path)
    with os.fdopen(fd,'r') as f:return json.load(f)

def _darwin_acl(fd,restore=None,read_only=False):
    libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
    libc.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int];libc.acl_get_fd_np.restype=ctypes.c_void_p
    libc.acl_to_text.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ssize_t)];libc.acl_to_text.restype=ctypes.c_void_p
    libc.acl_from_text.argtypes=[ctypes.c_char_p];libc.acl_from_text.restype=ctypes.c_void_p
    libc.acl_init.argtypes=[ctypes.c_int];libc.acl_init.restype=ctypes.c_void_p
    libc.acl_set_fd_np.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_int]
    libc.acl_free.argtypes=[ctypes.c_void_p]
    original=libc.acl_get_fd_np(fd,0x100)
    if not original:
        if ctypes.get_errno()!=errno.ENOENT:raise ValueError('source_acl_unsupported')
        saved=''  # macOS reports ENOENT for a regular file without an ACL.
    else:
        length=ctypes.c_ssize_t();text=libc.acl_to_text(original,ctypes.byref(length))
        if not text:libc.acl_free(original);raise ValueError('source_acl_unsupported')
        saved=ctypes.string_at(text,length.value).decode();libc.acl_free(text);libc.acl_free(original)
    if read_only:return saved
    acl=libc.acl_from_text(restore.encode()) if restore else libc.acl_init(0)
    try:
        if not acl or libc.acl_set_fd_np(fd,acl,0x100)!=0:raise ValueError('source_acl_unsupported')
    finally:
        if acl:libc.acl_free(acl)
    return saved

def _holders(st):
    """Detect already-open descriptors/maps after sealing; never publish names."""
    if sys.platform=='linux':
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if proc.stat().st_uid==0:continue
                for fd in (proc/'fd').iterdir():
                    try:s=fd.stat()
                    except FileNotFoundError:continue
                    if (s.st_dev,s.st_ino)==(st.st_dev,st.st_ino):return True
                for line in (proc/'maps').read_text().splitlines():
                    parts=line.split(maxsplit=5)
                    if len(parts)>4 and int(parts[4])==st.st_ino:
                        major,minor=parts[3].split(':')
                        if os.makedev(int(major,16),int(minor,16))==st.st_dev:return True
            except (FileNotFoundError,ProcessLookupError):continue
            except (PermissionError,OSError):raise ValueError('source_busy') from None
        return False
    if sys.platform=='darwin':
        p=subprocess.run(['/usr/sbin/lsof','-nP','-F','puDi'],capture_output=True,timeout=30,env={'PATH':'/usr/bin:/bin:/usr/sbin'})
        if p.returncode not in (0,1):raise ValueError('source_busy')
        uid=dev=None
        for line in p.stdout.decode(errors='strict').splitlines():
            if line.startswith('p'):uid=dev=None
            elif line.startswith('u'):uid=int(line[1:])
            elif line.startswith('D'):dev=int(line[1:],16)
            elif line.startswith('i') and uid not in (None,0) and dev==st.st_dev and int(line[1:])==st.st_ino:return True
        return False
    raise ValueError('unsupported_platform')

def denied_as_user(path,uid,gid):
    """Probe in a fresh reduced-privilege process, never fork Python service threads."""
    root_only()
    if uid<=0:raise ValueError('protection_unavailable')
    p=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'probe'],
                     input=json.dumps({'path':str(path)}).encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                     user=uid,group=gid,extra_groups=[],close_fds=True,timeout=30,
                     env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    return p.returncode==0 and p.stdout==b'1'


def seal(source,job,uid,gid,max_bytes,previous=None):
    root_only();job=secure_dir(job);source=Path(source)
    # Sources are local regular files owned by the enrolled desktop user.
    fd=open_regular(source)
    try:
        before=os.fstat(fd)
        reuse=previous is not None
        if reuse:
            if before.st_uid!=0 or previous.get('stage')!='verified' or previous.get('uid')!=uid or (before.st_dev,before.st_ino)!=(previous['dev'],previous['ino']):raise ValueError('source_not_owned')
        elif before.st_uid!=uid:raise ValueError('source_not_owned')
        if before.st_size>max_bytes:raise ValueError('source_too_large')
        local_filesystem(fd)
        record={'source':str(source),'dev':before.st_dev,'ino':before.st_ino,'uid':before.st_uid,'gid':before.st_gid,
                'mode':stat.S_IMODE(before.st_mode),'stage':'claiming','size':before.st_size}
        if reuse:record.update(uid=previous['uid'],gid=previous['gid'],mode=previous['mode'])
        if reuse and 'acl' in previous:record['acl']=previous['acl']
        # Journal before changing source permissions; crash recovery never auto-unseals.
        if sys.platform=='darwin' and not reuse:
            record['acl']=_darwin_acl(fd,read_only=True)
        atomic_json(job/'source-journal.json',record)
        if sys.platform=='darwin':_darwin_acl(fd)
        os.fchmod(fd,0);os.fchown(fd,0,0);os.fchmod(fd,0o600)
        sealed=os.fstat(fd)
        if sealed.st_uid!=0 or stat.S_IMODE(sealed.st_mode)!=0o600 or sealed.st_nlink!=1:raise ValueError('permission_probe_failed')
        record['stage']='sealed';atomic_json(job/'source-journal.json',record)
        if _holders(sealed):raise ValueError('source_busy')
        current=source.lstat()
        if (current.st_dev,current.st_ino)!=(before.st_dev,before.st_ino):raise ValueError('source_changed')
        if not denied_as_user(str(source),uid,gid):raise ValueError('permission_probe_failed')
        # Read plaintext only after kernel denial and open-handle checks have passed.
        data=os.read(fd,max_bytes+1)
        if len(data)>max_bytes:raise ValueError('source_too_large')
        after=os.fstat(fd)
        if after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns:raise ValueError('source_changed')
        if reuse and hashlib.sha256(data).hexdigest()!=previous['sha256']:raise ValueError('source_changed')
        snapshot=job/('original'+source.suffix.lower())
        out=os.open(snapshot,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(out,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        record.update(stage='verified',sha256=hashlib.sha256(data).hexdigest(),snapshot=snapshot.name)
        atomic_json(job/'source-journal.json',record)
        return snapshot
    finally:os.close(fd)

def restore(job,uid,gid):
    """Private human action only; reopening access is never automatic on an error."""
    record=get_json(Path(job)/'source-journal.json');fd=open_regular(record['source'])
    try:
        s=os.fstat(fd)
        if (s.st_dev,s.st_ino)!=(record['dev'],record['ino']):raise ValueError('source_changed')
        if record['uid']!=uid:raise ValueError('forbidden')
        if 'acl' in record:_darwin_acl(fd,record['acl'])
        os.fchown(fd,uid,record['gid']);os.fchmod(fd,record['mode'])
    finally:os.close(fd)
    record['stage']='released_by_user';atomic_json(Path(job)/'source-journal.json',record)

def export_file(source,destination,uid,gid):
    """An explicit private UI confirmation releases a result, never the original."""
    root_only();source=Path(source);dest=Path(destination)
    if not dest.is_absolute() or dest.suffix.lower()!=source.suffix.lower() or '..' in dest.parts:raise ValueError('export_target_invalid')
    fd=open_regular(source)
    try:
        p=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'export',str(fd)],
                         input=json.dumps({'path':str(dest)}).encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                         user=uid,group=gid,extra_groups=[],close_fds=True,pass_fds=(fd,),timeout=30,
                         env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        if p.returncode or p.stdout!=b'1':raise ValueError('export_target_invalid')
    finally:os.close(fd)


def local_filesystem(fd):
    if sys.platform=='linux':
        libc=ctypes.CDLL(None,use_errno=True);buf=ctypes.create_string_buffer(4096)
        if libc.fstatfs(fd,ctypes.byref(buf)):raise ValueError('source_not_local')
        kind=ctypes.c_long.from_buffer(buf).value & 0xffffffff
        if kind not in (0xef53,0x58465342,0x9123683e,0x01021994):raise ValueError('source_not_local')
    elif sys.platform=='darwin':
        class StatFS(ctypes.Structure):
            _fields_=[('bsize',ctypes.c_uint32),('iosize',ctypes.c_int32),('blocks',ctypes.c_uint64),
                      ('bfree',ctypes.c_uint64),('bavail',ctypes.c_uint64),('files',ctypes.c_uint64),
                      ('ffree',ctypes.c_uint64),('fsid',ctypes.c_int32*2),('owner',ctypes.c_uint32),
                      ('type',ctypes.c_uint32),('flags',ctypes.c_uint32),('subtype',ctypes.c_uint32),
                      ('fstypename',ctypes.c_char*16),('mntonname',ctypes.c_char*1024),
                      ('mntfromname',ctypes.c_char*1024),('flags_ext',ctypes.c_uint32),('reserved',ctypes.c_uint32*7)]
        libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True);info=StatFS()
        fn=libc.fstatfs;fn.argtypes=[ctypes.c_int,ctypes.POINTER(StatFS)]
        if fn(fd,ctypes.byref(info)) or not info.flags & 0x1000 or info.fstypename not in (b'apfs',b'hfs'):raise ValueError('source_not_local')
    else:raise ValueError('unsupported_platform')


def _reduced_helper():
    if os.geteuid()==0:sys.exit(2)
    request=json.loads(sys.stdin.buffer.read(8193));path=Path(request['path'])
    if set(request)!={'path'} or not path.is_absolute() or '..' in path.parts:sys.exit(2)
    if sys.argv[1]=='probe':
        checks=[]
        for op in (lambda:os.close(os.open(path,os.O_RDONLY)),lambda:os.chmod(path,0o600),lambda:os.chown(path,os.getuid(),os.getgid())):
            try:op();checks.append(False)
            except PermissionError:checks.append(True)
            except OSError:checks.append(False)
        sys.stdout.buffer.write(b'1' if all(checks) else b'0');return
    if sys.argv[1]!='export':sys.exit(2)
    data_fd=int(sys.argv[2]);directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=child
        if os.fstat(directory).st_uid!=os.getuid():raise ValueError('export_target_invalid')
        out=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(out,'wb') as f:
            while True:
                chunk=os.read(data_fd,1024*1024)
                if not chunk:break
                f.write(chunk)
            f.flush();os.fsync(f.fileno())
        os.fsync(directory)
    finally:os.close(directory)
    sys.stdout.buffer.write(b'1')

if __name__=='__main__':
    try:_reduced_helper()
    except Exception:sys.exit(2)


def owner_id(path):return Path(path).lstat().st_uid

def file_identity(path):
    s=Path(path).lstat();return s.st_dev,s.st_ino

def assert_private_file(path):
    s=Path(path).lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)&0o077 or s.st_nlink!=1:raise ValueError('private_store_insecure')
