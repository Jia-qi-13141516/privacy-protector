"""Local named pipes with kernel client identity and a verified SYSTEM server."""
import hashlib,json,threading
import protocol
import win32event
from windows_native import *

def endpoint(sid,private=False):
    return r'\\.\pipe\PrivacyProtector-'+hashlib.sha256(sid.encode()).hexdigest()[:16]+('-private' if private else '-public')
CLIENT_ACCESS=rights.FILE_GENERIC_READ|rights.FILE_WRITE_DATA|rights.FILE_WRITE_ATTRIBUTES

def server_is_system(handle,private=False):
    # Ordinary users cannot query SYSTEM process tokens. Verify the actual pipe
    # owner AND the complete DACL instead: no other identity may create server
    # instances or change ownership/ACLs, so owner checks cannot be spoofed by
    # adding a second instance under a genuine SYSTEM-owned pipe name.
    sd=win32security.GetSecurityInfo(handle,win32security.SE_KERNEL_OBJECT,win32security.OWNER_SECURITY_INFORMATION|win32security.DACL_SECURITY_INFORMATION)
    acl=sd.GetSecurityDescriptorDacl()
    if owner(sd)!=SYSTEM or acl is None or acl.GetAceCount()!=(1 if private else 2):raise ValueError('protection_unavailable')
    system_entries=0
    for i in range(acl.GetAceCount()):
        ace=acl.GetAce(i)
        if ace[0][0]!=0:raise ValueError('protection_unavailable')
        if win32security.ConvertSidToStringSid(ace[2])==SYSTEM:
            system_entries+=1
            if ace[1]!=rights.FILE_ALL_ACCESS:raise ValueError('protection_unavailable')
        elif private or ace[1]!=CLIENT_ACCESS:raise ValueError('protection_unavailable')
    if system_entries!=1:raise ValueError('protection_unavailable')
def io_operation(handle,operation,timeout=10000):
    """Bounded overlapped IO; a connected but silent Agent cannot stall the service."""
    ov=pywintypes.OVERLAPPED();ov.hEvent=win32event.CreateEvent(None,True,False,None)
    pending=None
    try:
        pending=operation(ov)
        if win32event.WaitForSingleObject(ov.hEvent,timeout)!=win32event.WAIT_OBJECT_0:
            # Every operation on this handle is issued by this thread.
            win32file.CancelIo(handle)
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
    h=win32file.CreateFile(str(path),rights.FILE_GENERIC_READ|rights.FILE_WRITE_DATA|rights.FILE_WRITE_ATTRIBUTES,0,None,win32con.OPEN_EXISTING,win32con.SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION|win32con.FILE_FLAG_OVERLAPPED,None)
    try:
        server_is_system(h,private);win32pipe.SetNamedPipeHandleState(h,win32pipe.PIPE_READMODE_MESSAGE,None,None)
        write_message(h,data)
        reply=json.loads(read_message(h,500000 if private else 4096).decode('utf-8'))
        write_message(h,b'\x06');return reply
    finally:h.Close()
def serve(sid,handler,private=False):
    root_only();name=endpoint(sid,private)
    # Public task/status IPC accepts the enrolled ordinary (medium-integrity)
    # user. SYSTEM's default integrity label would deny that intended write even
    # with the correct DACL. Private material IPC remains SYSTEM-only.
    access=rights.FILE_GENERIC_READ|rights.FILE_WRITE_DATA|rights.FILE_WRITE_ATTRIBUTES
    sddl='O:SYG:SYD:(A;;FA;;;SY)'
    if not private:
        win32security.ConvertStringSidToSid(sid)
        sddl+='(A;;0x'+format(access,'x')+';;;'+sid+')S:(ML;;NW;;;ME)'
    sd=win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(sddl,1)
    sa=pywintypes.SECURITY_ATTRIBUTES();sa.SECURITY_DESCRIPTOR=sd
    while True:
        pipe=win32pipe.CreateNamedPipe(name,win32pipe.PIPE_ACCESS_DUPLEX|0x00080000|win32con.FILE_FLAG_OVERLAPPED,
              win32pipe.PIPE_TYPE_MESSAGE|win32pipe.PIPE_READMODE_MESSAGE|win32pipe.PIPE_WAIT|8,1,500000,8193,10000,sa)
        try:
            try:io_operation(pipe,lambda ov:win32pipe.ConnectNamedPipe(pipe,ov),win32event.INFINITE)
            except pywintypes.error as e:
                if e.winerror!=535:raise
            try:
                data=read_message(pipe,8193)
                win32security.ImpersonateNamedPipeClient(pipe)
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
            # Disconnect would discard an unread reply; a bounded receipt avoids
            # FlushFileBuffers' unbounded wait on an untrusted client.
            if read_message(pipe,1)!=b'\x06':raise ValueError('ipc_failed')
        except (pywintypes.error,ValueError):pass
        finally:
            try:win32pipe.DisconnectNamedPipe(pipe)
            except pywintypes.error:pass
            pipe.Close()
