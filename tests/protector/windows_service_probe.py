"""Production Windows SCM lifecycle, disposable GitHub-hosted machines only."""
import hashlib,json,os,re,sys,time,uuid
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO_ROOT/'privacy-assistant/protector'))
if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':raise SystemExit('disposable CI only')
from windows_native import *
import windows_rpc as rpc,win32net
root_only();privilege(win32security.SE_RESTORE_NAME)
name='pp'+uuid.uuid4().hex[:12];password=uuid.uuid4().hex+'aA1!'
win32net.NetUserAdd(None,1,{'name':name,'password':password,'priv':1,'home_dir':'','comment':'Disposable synthetic test','flags':0x10001,'script_path':''})
token=None
try:
 token=win32security.LogonUser(name,'.',password,win32con.LOGON32_LOGON_INTERACTIVE,win32con.LOGON32_PROVIDER_DEFAULT);sid=token_sid(token)
 def user_read(p):
  with impersonate(token):
   try:return Path(p).read_bytes()
   except PermissionError:return None
 report={'scope':'Windows SCM lifecycle only; no VM processing or interactive desktop acceptance','fictional_only':True}
 import install_windows,win32service
 from install_common import install_plan,VERSION
 source_root=REPO_ROOT/'privacy-assistant';manifest=hashlib.sha256((source_root/'release.json').read_bytes()).hexdigest()
 installed=Path(install_plan('win32',sid,'AMD64')['base'])
 assert not installed.exists(),'fresh runner required'
 manager=win32service.OpenSCManager(None,None,win32service.SC_MANAGER_ALL_ACCESS);svc=None
 try:
  first=install_windows.install(source_root,sid,manifest,test=True)
  assert first=={'phase':'preparing','service_registered':True,'ready':False},first
  svc=win32service.OpenService(manager,'PrivacyProtector',win32service.SERVICE_ALL_ACCESS)
  config=win32service.QueryServiceConfig(svc)
  assert config[1]==win32service.SERVICE_AUTO_START and config[7] in ('LocalSystem',None),config
  assert str(installed/'App'/VERSION/'runtime/python.exe').lower() in config[3].lower(),config[3]
  config_file=installed/'State/config.json'
  assert user_read(config_file) is None
  exe=installed/'App'/VERSION/'runtime/python.exe'
  with impersonate(token):
   try:
    h=win32file.CreateFile(str(exe),rights.FILE_WRITE_DATA,7,None,win32con.OPEN_EXISTING,0,None);h.Close();raise AssertionError('service executable writable')
   except pywintypes.error as e:assert e.winerror==5,e
  def health():
   until=time.monotonic()+60
   while True:
    try:
     with impersonate(token):return rpc.request(rpc.endpoint(sid),{'action':'health'})
    except Exception:
     if time.monotonic()>until:raise
     time.sleep(.5)
  status=health()
  assert status.get('ready') is False and status.get('phase') in ('preparing','downloading_runtime','downloading_model','verifying_access','blocked'),status
  with impersonate(token):refused=rpc.request(rpc.endpoint(sid),{'action':'submit','task':'Fictional test only'})
  assert refused=={'error':'not_ready'},refused
  win32service.ControlService(svc,win32service.SERVICE_CONTROL_STOP)
  until=time.monotonic()+30
  while win32service.QueryServiceStatus(svc)[1]!=win32service.SERVICE_STOPPED:
   assert time.monotonic()<until,'service stop timeout';time.sleep(.2)
  repeat=install_windows.install(source_root,sid,manifest,test=True);assert repeat['service_registered']
  again=health();assert again.get('ready') is False,again
  # Observe the real automatic preparation outcome. A blocked environment is
  # reported as blocked, never as a completed document/table workflow.
  deadline=time.monotonic()+600;last_phase=None
  while True:
   status=health()
   if status.get('phase')!=last_phase:
    print(json.dumps({'readiness_phase':status.get('phase'),'code':status.get('code')}),flush=True);last_phase=status.get('phase')
   if status.get('phase') in ('ready','blocked') or time.monotonic()>=deadline:break
   time.sleep(3)
  diagnostic=installed/'State/Jobs/readiness-error.json'
  if diagnostic.exists():report['private_structural_diagnostic']=json.loads(diagnostic.read_text(encoding='utf-8'))
  if status.get('phase') not in ('ready','blocked'):
   # Only fixed VM state fields and error-code tokens leave this synthetic CI.
   # Do not publish VBox logs, paths, guest credentials or command output.
   sys.path.insert(0,str(source_root/'scripts'))
   from vm_backend import Backend
   try:
    backend=Backend(installed/'State/Offline');info=backend.info('offline')
    report['vm_observation']={key:info.get(key) for key in ('VMState','memory','cpus','nic1','hwvirtex','nestedpaging','effectiveparavirtprovider')}
   except Exception as error:report['vm_observation']={'query_error_type':type(error).__name__}
   codes=set()
   for log in (installed/'State/Offline/Machines').rglob('VBox.log'):
    with log.open('rb') as stream:
     stream.seek(max(0,log.stat().st_size-262144));data=stream.read(262144).decode('utf-8',errors='ignore')
    codes.update(re.findall(r'\bVERR_[A-Z0-9_]+\b',data))
   report['hypervisor_error_codes']=sorted(codes)
  report['automatic_preparation']={'ready':status.get('ready') is True,'phase':status.get('phase'),'code':status.get('code'),'observation_timed_out':status.get('phase') not in ('ready','blocked'),'self_test_passed':status.get('self_test_passed') is True,'business_material_submitted':False}
  report['service']={'production_installer':True,'bundled_interpreter':True,'system_identity_autostart':True,'ordinary_user_config_denied':True,'executable_write_denied':True,'health_rpc':True,'pre_ready_task_rejected':True,'stop_repeat_install_and_restart':True,'first_phase':status.get('phase'),'restart_phase':again.get('phase'),'first_code':status.get('code'),'restart_code':again.get('code'),'vm_processing_tested':False,'interactive_ui_tested':False}
 finally:
  diagnostic=installed/'State/Jobs/readiness-error.json'
  if diagnostic.exists():print(diagnostic.read_text(encoding='utf-8'),flush=True)
  if svc:
   try:win32service.ControlService(svc,win32service.SERVICE_CONTROL_STOP)
   except pywintypes.error:pass
   svc.Close()
  manager.Close()
 Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
finally:
 if token:token.Close()
 try:win32net.NetUserDel(None,name)
 except Exception:pass
