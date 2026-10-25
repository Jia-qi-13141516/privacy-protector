"""Kernel-verified local IPC. A user-owned socket or a claimed UID is not trusted."""
import json,os,socket,stat,struct,sys,threading
from pathlib import Path
import protocol

def peer_uid(sock):
    if sys.platform=='linux':return struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
    if sys.platform=='darwin':
        import ctypes
        libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True);uid=ctypes.c_uint();gid=ctypes.c_uint()
        if libc.getpeereid(sock.fileno(),ctypes.byref(uid),ctypes.byref(gid)):raise ValueError('forbidden')
        return uid.value
    raise ValueError('unsupported_platform')

def receive(sock,limit):
    data=b''
    while b'\n' not in data:
        chunk=sock.recv(min(4096,limit+1-len(data)))
        if not chunk:raise ValueError('invalid_request')
        data+=chunk
        if len(data)>limit:raise ValueError('invalid_request')
    line,extra=data.split(b'\n',1)
    if extra:raise ValueError('invalid_request')
    return line

def trusted_parent(path):
    p=Path(path)
    for item in [p,*p.parents]:
        s=item.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise ValueError('protection_unavailable')

def request(path,obj,private=False):
    path=Path(path);trusted_parent(path.parent)
    st=path.lstat()
    if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=0:raise ValueError('protection_unavailable')
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(120 if private else 10)
    try:
        sock.connect(str(path))
        if peer_uid(sock)!=0:raise ValueError('protection_unavailable')
        encoded=json.dumps(obj,ensure_ascii=False).encode()
        if len(encoded)>protocol.MAX_REQUEST:raise ValueError('invalid_request')
        sock.sendall(encoded+b'\n')
        limit=500000 if private else 4096
        return json.loads(receive(sock,limit))
    finally:sock.close()

def serve(path,handler,private=False):
    if os.geteuid()!=0:raise ValueError('protection_unavailable')
    path=Path(path);trusted_parent(path.parent)
    if path.exists():
        st=path.lstat()
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=0:raise ValueError('private_store_insecure')
        path.unlink()
    sock=socket.socket(socket.AF_UNIX);sock.bind(str(path));os.chmod(path,0o600 if private else 0o666);sock.listen(8)
    def handle(conn):
        with conn:
            conn.settimeout(10)
            try:
                uid=peer_uid(conn)
                if private and uid!=0:raise ValueError('forbidden')
                obj=protocol.decode(receive(conn,protocol.MAX_REQUEST));reply=handler(obj,uid)
            except Exception as error:reply=protocol.failure(error)
            try:conn.sendall(json.dumps(reply,ensure_ascii=False).encode()+b'\n')
            except OSError:pass
    try:
        while True:
            conn,_=sock.accept();handle(conn)
    finally:sock.close()
