"""Run with the ordinary Agent identity inside the disposable VM, never as root."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,'/opt/privacy-protector/protector')
import unix_rpc
request=json.loads(sys.stdin.read());out={}
assert os.geteuid()!=0
for name,path in request.get('files',{}).items():
 for action in ('read','chmod','chown'):
  try:
   if action=='read':Path(path).read_bytes()
   elif action=='chmod':os.chmod(path,0o600)
   else:os.chown(path,os.geteuid(),os.getgid())
   out[name+':'+action]=False
  except PermissionError:out[name+':'+action]=True
  except OSError:out[name+':'+action]=False
for index,obj in enumerate(request.get('public_requests',[])):
 try:out['public:'+str(index)]=unix_rpc.request('/run/privacy-protector-test/public.sock',obj)
 except Exception as e:out['public:'+str(index)]={'error':str(e)}
if request.get('try_private'):
 try:unix_rpc.request('/run/privacy-protector-test/private.sock',{'action':'restore','id':request['id']},private=True);out['private_denied']=False
 except PermissionError:out['private_denied']=True
 except Exception:out['private_denied']=False
print(json.dumps(out))
