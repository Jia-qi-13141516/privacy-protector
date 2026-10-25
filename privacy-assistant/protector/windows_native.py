"""Windows API imports, service identity and handles. No setup runs at import time."""
import contextlib,os,sys
from pathlib import Path
if sys.platform!='win32':raise ImportError('Windows only')
ROOT=Path(__file__).resolve().parents[1]
lib=ROOT/'runtime/Lib/site-packages'
sys.path[:0]=[str(lib),str(lib/'win32'),str(lib/'win32/lib'),str(lib/'Pythonwin')]
_DLL=os.add_dll_directory(str(lib/'pywin32_system32')) if (lib/'pywin32_system32').is_dir() else None
import pywintypes,win32api,win32con,win32file,win32security,win32pipe,win32process,win32ts
SYSTEM='S-1-5-18'
SEC=win32security.OWNER_SECURITY_INFORMATION|win32security.GROUP_SECURITY_INFORMATION|win32security.DACL_SECURITY_INFORMATION

def token_sid(token):return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
def current_sid():
    t=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:return token_sid(t)
    finally:t.Close()
def root_only():
    if current_sid()!=SYSTEM:raise ValueError('protection_unavailable')
def privilege(name):
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_ADJUST_PRIVILEGES|win32con.TOKEN_QUERY)
    try:win32security.AdjustTokenPrivileges(token,False,[(win32security.LookupPrivilegeValue(None,name),win32con.SE_PRIVILEGE_ENABLED)])
    finally:token.Close()
def active_token(sid):
    root_only();session=win32ts.WTSGetActiveConsoleSessionId()
    if session==0xffffffff:raise ValueError('ui_unavailable')
    token=win32ts.WTSQueryUserToken(session)
    if token_sid(token)!=sid:token.Close();raise ValueError('ui_unavailable')
    return token
@contextlib.contextmanager
def impersonate(token):
    win32security.ImpersonateLoggedOnUser(token)
    try:yield
    finally:win32security.RevertToSelf()
def system_acl():
    acl=win32security.ACL();acl.AddAccessAllowedAceEx(win32security.ACL_REVISION,win32con.OBJECT_INHERIT_ACE|win32con.CONTAINER_INHERIT_ACE,win32con.FILE_ALL_ACCESS,win32security.ConvertStringSidToSid(SYSTEM));return acl

def protect(path,readable=False):
    root_only();acl=system_acl()
    if readable:acl.AddAccessAllowedAceEx(win32security.ACL_REVISION,3,win32con.FILE_GENERIC_READ|win32con.FILE_GENERIC_EXECUTE,win32security.CreateWellKnownSid(win32security.WinBuiltinUsersSid,None))
    win32security.SetNamedSecurityInfo(str(path),win32security.SE_FILE_OBJECT,win32security.OWNER_SECURITY_INFORMATION|win32security.DACL_SECURITY_INFORMATION|win32security.PROTECTED_DACL_SECURITY_INFORMATION,win32security.ConvertStringSidToSid(SYSTEM),None,acl,None)

def local_path(path):
    p=Path(path);s=str(p)
    if not p.is_absolute() or len(p.drive)!=2 or p.drive[1]!=':' or s.startswith('\\\\') or ':' in s[2:] or '..' in p.parts:raise ValueError('linked_source')
    if win32file.GetDriveType(p.anchor)!=win32con.DRIVE_FIXED:raise ValueError('source_not_local')
    info=win32api.GetVolumeInformation(p.anchor)
    if info[-1] not in ('NTFS','ReFS') or not info[3]&8:raise ValueError('source_not_local')
    return p
@contextlib.contextmanager
def anchored(path,access=win32con.GENERIC_READ,exclusive=False):
    p=local_path(path);parents=[];handle=None
    try:
        # Keeping every ancestor open without FILE_SHARE_DELETE prevents renames
        # and reparse-point swaps while the leaf is inspected/changed/read.
        for parent in reversed(p.parents):
            h=win32file.CreateFile(str(parent),win32con.FILE_READ_ATTRIBUTES,3,None,win32con.OPEN_EXISTING,win32con.FILE_FLAG_BACKUP_SEMANTICS|win32con.FILE_FLAG_OPEN_REPARSE_POINT,None);parents.append(h)
            if win32file.GetFileInformationByHandle(h)[0]&win32con.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('linked_source')
        handle=win32file.CreateFile(str(p),access,0 if exclusive else 7,None,win32con.OPEN_EXISTING,win32con.FILE_FLAG_OPEN_REPARSE_POINT,None)
        info=win32file.GetFileInformationByHandle(handle)
        if info[0]&(win32con.FILE_ATTRIBUTE_REPARSE_POINT|win32con.FILE_ATTRIBUTE_DIRECTORY) or info[7]!=1:raise ValueError('linked_source')
        yield handle,info
    except pywintypes.error as error:
        if error.winerror in (32,33):raise ValueError('source_busy') from None
        if error.winerror==5:raise PermissionError('access_denied') from None
        raise
    finally:
        if handle is not None:handle.Close()
        for h in reversed(parents):h.Close()
def identity(info):return info[4],(info[8]<<32)|info[9]
def descriptor(handle):return win32security.GetSecurityInfo(handle,win32security.SE_FILE_OBJECT,SEC)
def owner(sd):return win32security.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner())
def private_descriptor(sd):
    acl=sd.GetSecurityDescriptorDacl()
    return owner(sd)==SYSTEM and acl is not None and acl.GetAceCount()==1 and win32security.ConvertSidToStringSid(acl.GetAce(0)[2])==SYSTEM and acl.GetAce(0)[0][0]==0 and acl.GetAce(0)[1]==win32con.FILE_ALL_ACCESS


def assert_installed_tree(root):
    """All service-importable files are SYSTEM owned, users read/execute only."""
    root_only();root=local_path(root)
    user_sid=win32security.ConvertSidToStringSid(win32security.CreateWellKnownSid(win32security.WinBuiltinUsersSid,None))
    allowed={SYSTEM:win32con.FILE_ALL_ACCESS,user_sid:win32con.FILE_GENERIC_READ|win32con.FILE_GENERIC_EXECUTE}
    for p in (root.parent.parent,root.parent,root,*root.rglob('*')):
        if win32file.GetFileAttributes(str(p))&win32con.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('private_store_insecure')
        sd=win32security.GetNamedSecurityInfo(str(p),win32security.SE_FILE_OBJECT,SEC);acl=sd.GetSecurityDescriptorDacl()
        if owner(sd)!=SYSTEM or acl is None or acl.GetAceCount()!=2:raise ValueError('private_store_insecure')
        for i in range(acl.GetAceCount()):
            ace=acl.GetAce(i)
            if ace[0][0]!=0 or allowed.get(win32security.ConvertSidToStringSid(ace[2]))!=ace[1]:raise ValueError('private_store_insecure')
