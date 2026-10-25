"""Local named pipes with kernel client identity and a verified SYSTEM server."""
import hashlib,json,threading
import protocol
import win32event
from windows_native import *

def endpoint(sid,private=False):
    return r'\\.\pipe\PrivacyProtector-'+hashlib.sha256(sid.encode()).hexdigest()[:16]+('-private' if private else '-public')
def server_is_system(handle):
    sd=win32security.GetSecurityInfo(handle,win32security.SE_FILE_OBJECT,win32security.OWNER_SECURITY_INFORMATION)
    if owner(sd)!=SYSTEM:raise ValueError('protection_unavailable')
    pid=win32pipe.GetNamedPipeServerProcessId(handle)
    process=win32api.OpenProcess(0x1000,False,pid)
    try:
        token=win32security.OpenProcessToken(process,win32con.TOKEN_QUERY)
        try:
            if token_sid(token)!=SYSTEM:raise ValueError('protection_unavailable')
        finally:token.Close()
    finally:process.Close()
def io_operation(handle,operation,timeout=10000):
    """Bounded overlapped IO; a connected but silent Agent cannot stall the service."""
    ov=pywintypes.OVERLAPPED();ov.hEvent=win32event.CreateEvent(None,True,False,None)
    pending=None
    try:
        pending=operation(ov)
        if win32event.WaitForSingleObject(ov.hEvent,timeout)!=win32event.WAIT_OBJECT_0:
            win32file.CancelIoEx(handle,ov)
            try:win32file.GetOverlappedResult(handle,ov,True)
            except pywintypes.error:pass
            raise ValueError('ipc_timeout')
        count=win32file.GetOverlappedResult(handle,ov,False)
        return count,pending
    finally:ov.hEvent.Close()

def read_message(handle,limit):
    buffer=win32file.AllocateReadBuffer(limit)
    count,_=io_operation(handle,lambda ov:win32file.ReadFile(handle,buffer,ov))
    return bytes(buffer[:count])
def write_message(handle,data):
    count,_=io_operation(handle,lambda ov:win32file.WriteFile(handle,data,ov))
    if count!=len(data):raise ValueError('ipc_failed')

def request(path,obj,private=False):
    protocol.private_request(obj) if private else protocol.public_request(obj)
    data=json.dumps(obj,ensure_ascii=False).encode()
    if len(data)>protocol.MAX_REQUEST:raise ValueError('invalid_request')
    win32pipe.WaitNamedPipe(str(path),10000)
    h=win32file.CreateFile(str(path),rights.FILE_READ_DATA|rights.FILE_WRITE_DATA|rights.FILE_WRITE_ATTRIBUTES|win32con.READ_CONTROL|win32con.SYNCHRONIZE,0,None,win32con.OPEN_EXISTING,win32con.SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION|win32con.FILE_FLAG_OVERLAPPED,None)
    try:
        server_is_system(h);win32pipe.SetNamedPipeHandleState(h,win32pipe.PIPE_READMODE_MESSAGE,None,None)
        write_message(h,data)
        return json.loads(read_message(h,500000 if private else 4096).decode('utf-8'))
    finally:h.Close()
def serve(sid,handler,private=False):
    root_only();name=endpoint(sid,private)
    sd=win32security.SECURITY_DESCRIPTOR();sd.SetSecurityDescriptorOwner(win32security.ConvertStringSidToSid(SYSTEM),False)
    acl=win32security.ACL();acl.AddAccessAllowedAce(win32security.ACL_REVISION,rights.FILE_ALL_ACCESS,win32security.ConvertStringSidToSid(SYSTEM))
    if not private:
        acl.AddAccessAllowedAce(win32security.ACL_REVISION,rights.FILE_READ_DATA|rights.FILE_WRITE_DATA|rights.FILE_WRITE_ATTRIBUTES|win32con.READ_CONTROL|win32con.SYNCHRONIZE,win32security.ConvertStringSidToSid(sid))
    sd.SetSecurityDescriptorDacl(1,acl,0);sa=pywintypes.SECURITY_ATTRIBUTES();sa.SECURITY_DESCRIPTOR=sd
    while True:
        pipe=win32pipe.CreateNamedPipe(name,win32pipe.PIPE_ACCESS_DUPLEX|0x00080000|win32con.FILE_FLAG_OVERLAPPED,
              win32pipe.PIPE_TYPE_MESSAGE|win32pipe.PIPE_READMODE_MESSAGE|win32pipe.PIPE_WAIT|8,1,500000,8193,10000,sa)
        try:
            try:io_operation(pipe,lambda ov:win32pipe.ConnectNamedPipe(pipe,ov),win32event.INFINITE)
            except pywintypes.error as e:
                if e.winerror!=535:raise
            try:
                data=read_message(pipe,8193)
                win32pipe.ImpersonateNamedPipeClient(pipe)
                try:
                    token=win32security.OpenThreadToken(win32api.GetCurrentThread(),win32con.TOKEN_QUERY,True)
                    try:
                        peer=token_sid(token)
                        if not private and win32security.GetTokenInformation(token,win32security.TokenElevation):raise ValueError('forbidden')
                    finally:token.Close()
                finally:win32security.RevertToSelf()
                if (private and peer!=SYSTEM) or (not private and peer!=sid):raise ValueError('forbidden')
                reply=handler(protocol.decode(data),0 if private else peer)
            except Exception as e:reply=protocol.failure(e)
            write_message(pipe,json.dumps(reply,ensure_ascii=False).encode())
        except (pywintypes.error,ValueError):pass
        finally:
            try:win32pipe.DisconnectNamedPipe(pipe)
            except pywintypes.error:pass
            pipe.Close()
