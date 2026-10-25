"""Actual Windows ACL and pipe probes, only on a disposable GitHub-hosted runner."""
import json,os,sys,tempfile,time,uuid,threading,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'privacy-assistant/protector'))
if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':raise SystemExit('disposable CI only')
from windows_native import *
import windows_store as store,windows_rpc as rpc,win32net
root_only();privilege(win32security.SE_RESTORE_NAME)
base=Path('C:/')/('PrivacyProtectorTest-'+uuid.uuid4().hex);base.mkdir()
name='pp'+uuid.uuid4().hex[:12];password=uuid.uuid4().hex+'aA1!'
win32net.NetUserAdd(None,1,{'name':name,'password':password,'priv':1,'home_dir':'','comment':'Disposable synthetic test','flags':0x10001,'script_path':''})
token=None
try:
 token=win32security.LogonUser(name,'.',password,win32con.LOGON32_LOGON_INTERACTIVE,win32con.LOGON32_PROVIDER_DEFAULT);sid=token_sid(token)
 def dup(uid):
  assert uid==sid
  return win32security.DuplicateTokenEx(token,win32security.SecurityImpersonation,win32con.TOKEN_ALL_ACCESS,win32security.TokenPrimary)
 store.USER_TOKEN=dup
 acl=system_acl();acl.AddAccessAllowedAceEx(win32security.ACL_REVISION,3,rights.FILE_ALL_ACCESS,win32security.ConvertStringSidToSid(sid))
 win32security.SetNamedSecurityInfo(str(base),win32security.SE_FILE_OBJECT,win32security.DACL_SECURITY_INFORMATION|win32security.PROTECTED_DACL_SECURITY_INFORMATION,None,None,acl,None)
 private=base/'private';private.mkdir();protect(private);job=private/'job';job.mkdir();protect(job)
 source=base/'fictional.csv';data=b'id,name,count\n001,SYNTHETIC_ONLY,3\n'
 with impersonate(token):source.write_bytes(data)
 def user_read(p):
  with impersonate(token):
   try:return Path(p).read_bytes()
   except PermissionError:return None
 assert user_read(source)==data
 snapshot=store.seal(source,job,sid,None,100000)
 assert user_read(source) is None and user_read(snapshot) is None and store.denied_as_user(source,sid)
 assert snapshot.read_bytes()==data
 result=job/'result.csv';result.write_bytes(data);store.assert_private_file(result)
 export=base/'approved.csv';store.export_file(result,export,sid);assert user_read(export)==data
 try:store.export_file(result,export,sid);raise AssertionError('overwritten')
 except ValueError:assert export.read_bytes()==data
 store.restore(job,sid);assert user_read(source)==data
 # Sharing violations are refused before creating a protected snapshot.
 busy=base/'busy.csv'
 with impersonate(token):busy.write_bytes(data);held=win32file.CreateFile(str(busy),win32con.GENERIC_READ,7,None,win32con.OPEN_EXISTING,0,None)
 j=private/'busy';j.mkdir();protect(j)
 try:
  try:store.seal(busy,j,sid,None,100000);raise AssertionError('open file accepted')
  except ValueError as e:assert str(e)=='source_busy'
  assert not (j/'original.csv').exists()
 finally:held.Close()
 # Public messages are authenticated using the actual pipe client token.
 def handler(obj,peer):return {'peer_matches':peer==sid,'ready':True}
 threading.Thread(target=rpc.serve,args=(sid,handler),daemon=True).start()
 for _ in range(30):
  try:
   with impersonate(token):reply=rpc.request(rpc.endpoint(sid),{'action':'health'})
   break
  except Exception:
   if _==29:raise
   time.sleep(.1)
 assert reply=={'peer_matches':True,'ready':True},reply
 threading.Thread(target=rpc.serve,args=(sid,lambda obj,peer:{'private':True},True),daemon=True).start();time.sleep(.2)
 with impersonate(token):
  try:rpc.request(rpc.endpoint(sid,True),{'action':'review','id':'a'*32},private=True);raise AssertionError('private pipe accepted')
  except pywintypes.error as e:assert e.winerror==5,e
 # A SYSTEM-owned pipe is insufficient if clients can create additional
 # server instances. Validate the actual kernel descriptor against this attack.
 unsafe=rpc.endpoint(sid)+'-unsafe'
 sd=win32security.ConvertStringSecurityDescriptorToSecurityDescriptor('O:SYG:SYD:(A;;FA;;;SY)(A;;0x'+format(rpc.CLIENT_ACCESS|4,'x')+';;;'+sid+')S:(ML;;NW;;;ME)',1)
 sa=pywintypes.SECURITY_ATTRIBUTES();sa.SECURITY_DESCRIPTOR=sd
 bad=win32pipe.CreateNamedPipe(unsafe,win32pipe.PIPE_ACCESS_DUPLEX,win32pipe.PIPE_TYPE_MESSAGE|win32pipe.PIPE_READMODE_MESSAGE|8,1,1024,1024,1000,sa)
 try:
  try:rpc.server_is_system(bad);raise AssertionError('unsafe instance-creation ACL accepted')
  except ValueError as e:assert str(e)=='protection_unavailable'
 finally:bad.Close()
 report={'os':'Windows','kernel_acl':True,'ordinary_user_read_before_sealing':True,'ordinary_user_denied_after_sealing':True,'permission_changes_denied':True,'snapshot_denied':True,'confirmed_export_exact':True,'existing_export_preserved':True,'explicit_restore_exact':True,'open_handle_refused':True,'pipe_client_identity':True,'private_pipe_denied':True,'unsafe_server_instance_acl_rejected':True,'fictional_only':True,'ui_tested':False,'offline_vm_processing_tested':False}
 Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
finally:
 if token:token.Close()
 try:win32net.NetUserDel(None,name)
 except Exception:pass
