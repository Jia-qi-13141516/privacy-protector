"""A real Windows SCM service. Imported only by its immutable installed entry."""
import json,os,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from windows_native import *
import win32service,win32serviceutil,win32event,servicemanager
import protocol,windows_rpc,windows_store as permissions
from broker import Broker
from readiness import Readiness

CONFIG=Path(sys.argv[2]) if len(sys.argv)==3 and sys.argv[1]=='--config' else None

def show_window(config,mode,identifier):
    root_only();protocol.identifier(identifier)
    user=active_token(config['uid'])
    try:session=win32security.GetTokenInformation(user,win32security.TokenSessionId)
    finally:user.Close()
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_ALL_ACCESS)
    duplicate=win32security.DuplicateTokenEx(token,win32security.SecurityImpersonation,win32con.TOKEN_ALL_ACCESS,win32security.TokenPrimary)
    try:
        win32security.SetTokenInformation(duplicate,win32security.TokenSessionId,session)
        si=win32process.STARTUPINFO();si.lpDesktop='winsta0\\default'
        cmd=subprocess.list2cmdline([sys.executable,'-I','-B',str(Path(config['root'])/'protector/windows_ui.py'),mode,identifier,config['uid']])
        hp,ht,_,_=win32process.CreateProcessAsUser(duplicate,None,cmd,None,None,False,win32con.CREATE_NO_WINDOW,None,str(config['root']),si)
        hp.Close();ht.Close()
    finally:duplicate.Close();token.Close()

def serve(config_file):
    root_only();config=permissions.get_json(config_file);root=Path(config['root'])
    sys.path[:0]=[str(root/'scripts'),str(root/'skill/scripts'),str(root/'runtime/Lib/site-packages')]
    import performance,background_windows
    from windows_worker import Worker
    # Service executable and configuration were copied into SYSTEM-owned paths;
    # file manifests are checked again before accepting any task.
    from install_common import verify_tree
    assert_installed_tree(root);verify_tree(root)
    def capacity():
        backend=__import__('vm_backend').Backend(Path(config['state']))
        entry=backend.state['machines'].get('offline',{})
        running=bool(entry.get('ready') and backend.info('offline').get('VMState')=='running')
        performance.require_capacity(performance.hardware(),vm_running=running)
    def prepare(progress):
        state=Path(config['state']);permissions.secure_dir(state)
        backend=background_windows.prepare(state,progress)
        # Every VM disk, guest credential, request and response inherits SYSTEM-only ACLs.
        return Worker(root,state,backend)
    def probe():
        canary=Path(config['store'])/'startup-canary';canary.write_bytes(b'fictional startup probe')
        if not permissions.denied_as_user(canary,config['uid']):raise ValueError('permission_probe_failed')
    ready=Readiness(root,Path(config['store'])/'readiness.json',permissions,prepare,capacity,probe)
    broker=Broker(config['store'],ready,lambda mode,identifier:show_window(config,mode,identifier),config['uid'],None,permissions,ready)
    threading.Thread(target=windows_rpc.serve,args=(config['uid'],broker.private,True),daemon=True).start()
    ready.start();windows_rpc.serve(config['uid'],broker.public)

class Service(win32serviceutil.ServiceFramework):
    _svc_name_='PrivacyProtector'
    _svc_display_name_='Privacy Protector'
    def __init__(self,args):
        super().__init__(args);self.stop=win32event.CreateEvent(None,0,0,None)
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop)
    def SvcDoRun(self):
        if CONFIG is None:raise ValueError('invalid_request')
        threading.Thread(target=serve,args=(CONFIG,),daemon=True).start()
        win32event.WaitForSingleObject(self.stop,win32event.INFINITE)
        # Service process exit closes IPC. Journals and protected data persist;
        # interrupted jobs are blocked on restart and never implicitly unlocked.
        os._exit(0)

if __name__=='__main__':
    if CONFIG is None:sys.exit(2)
    servicemanager.Initialize();servicemanager.PrepareToHostSingle(Service);servicemanager.StartServiceCtrlDispatcher()
