"""First authorized Windows installation; persistent SYSTEM service, no second login."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from windows_native import *
import win32service
from install_common import VERSION,copy_verified,install_plan,qualification

def elevated():
    t=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:return bool(win32security.GetTokenInformation(t,win32security.TokenElevation))
    finally:t.Close()

def bootstrap_acl(path,private):
    # Initial installer runs with OS-granted admin rights. Ownership is assigned
    # to SYSTEM now; ordinary Agent tokens never own the service or its state.
    privilege(win32security.SE_RESTORE_NAME);privilege(win32security.SE_TAKE_OWNERSHIP_NAME)
    acl=system_acl()
    if not private:acl.AddAccessAllowedAceEx(win32security.ACL_REVISION,3,rights.FILE_GENERIC_READ|rights.FILE_GENERIC_EXECUTE,win32security.CreateWellKnownSid(win32security.WinBuiltinUsersSid,None))
    win32security.SetNamedSecurityInfo(str(path),win32security.SE_FILE_OBJECT,win32security.OWNER_SECURITY_INFORMATION|win32security.DACL_SECURITY_INFORMATION|win32security.PROTECTED_DACL_SECURITY_INFORMATION,win32security.ConvertStringSidToSid(SYSTEM),None,acl,None)

def install(source,sid,expected,test=False):
    if not elevated():raise ValueError('system_authorization_required')
    qualification(source,test)
    win32security.ConvertStringSidToSid(sid)
    if sid in (SYSTEM,'S-1-5-32-544'):raise ValueError('invalid_request')
    import platform
    plan=install_plan('win32',sid,platform.machine());base=Path(plan['base']);base.mkdir(parents=True,exist_ok=True)
    for p in (base,*base.parents):
        if win32file.GetFileAttributes(str(p))&win32con.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('private_store_insecure')
    # The elevated installer needs temporary admin rights while copying, before
    # the final SYSTEM-only state descriptor is applied and the service starts.
    app=copy_verified(source,base/'App',expected)
    state=Path(plan['state']);config=state/'config.json';enrollment=base/'enrollment.json'
    if enrollment.exists():
        info=json.loads(enrollment.read_text())
        sd=win32security.GetNamedSecurityInfo(str(enrollment),win32security.SE_FILE_OBJECT,SEC)
        if owner(sd)!=SYSTEM or info!={'sid':sid,'version':VERSION}:raise ValueError('existing_installation_preserved')
    else:
        if state.exists():raise ValueError('incomplete_installation_preserved')
        state.mkdir();store=state/'Jobs';store.mkdir();vmstate=state/'Offline';vmstate.mkdir()
        for name in ('Settings','Cache','Machines'):(vmstate/name).mkdir()
        value={'uid':sid,'root':str(app),'store':str(store),'state':str(vmstate)}
        config.write_text(json.dumps(value),encoding='utf-8')
        for p in sorted(state.rglob('*'),key=lambda p:len(p.parts),reverse=True):bootstrap_acl(p,True)
        bootstrap_acl(state,True)
        enrollment.write_text(json.dumps({'sid':sid,'version':VERSION}),encoding='utf-8')
        bootstrap_acl(enrollment,False)
    for p in sorted(app.rglob('*'),key=lambda p:len(p.parts),reverse=True):bootstrap_acl(p,False)
    bootstrap_acl(app,False);bootstrap_acl(base/'App',False);bootstrap_acl(enrollment,False);bootstrap_acl(base,False)
    executable=app/plan['python']
    command=subprocess.list2cmdline([str(executable),'-I','-B',str(app/'protector/windows_daemon.py'),'--config',str(config)])
    manager=win32service.OpenSCManager(None,None,win32service.SC_MANAGER_ALL_ACCESS)
    try:
        try:service=win32service.CreateService(manager,'PrivacyProtector','Privacy Protector',win32service.SERVICE_ALL_ACCESS,win32service.SERVICE_WIN32_OWN_PROCESS,win32service.SERVICE_AUTO_START,win32service.SERVICE_ERROR_NORMAL,command,None,0,None,None,None)
        except pywintypes.error as error:
            if error.winerror!=1073:raise
            service=win32service.OpenService(manager,'PrivacyProtector',win32service.SERVICE_START|win32service.SERVICE_QUERY_STATUS)
        try:
            try:win32service.StartService(service,None)
            except pywintypes.error as error:
                if error.winerror!=1056:raise
        finally:service.Close()
    finally:manager.Close()
    return {'phase':'preparing','service_registered':True,'ready':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--sid',required=True);p.add_argument('--manifest-sha',required=True);p.add_argument('--test-install',action='store_true');a=p.parse_args()
    try:r=install(Path(a.source),a.sid,a.manifest_sha,a.test_install)
    except Exception:r={'phase':'blocked','code':'installation_failed','ready':False}
    print(json.dumps(r));sys.exit(0 if r['phase']!='blocked' else 2)
