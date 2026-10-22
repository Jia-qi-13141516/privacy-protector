import base64,json,os,pwd,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,'/opt/privacy-bridge')
from network_policy import firewall
control=Path('/var/lib/privacy-control');queue=Path('/home/teacher/PrivacyTasks');queue.mkdir(exist_ok=True)
u=pwd.getpwnam('teacher');os.chown(queue,u.pw_uid,u.pw_gid)
Path('/etc/privacy-assistant-guest.json').write_text(json.dumps({'role':'online','queue':str(queue)}))
def rpc(request):
 id=uuid.uuid4().hex;(control/(id+'.json')).write_text(json.dumps(request))
 r=subprocess.run(['python3','-I','/opt/privacy-bridge/guest_rpc.py',id],capture_output=True,text=True,check=True)
 return json.loads(r.stdout)
# Execute this program inside a temporary network namespace, never the VM's main network.
subprocess.run(['nft','-f','/tmp/firewall-test.nft'],check=True)
subprocess.run(['python3','/opt/privacy-bridge/guest_health.py'],check=True)
assert rpc({'action':'health'})['status']=='online'
subprocess.run(['nft','flush','ruleset'],check=True)
assert 'error' in rpc({'action':'health'})
canary=control/'canary';canary.write_text('SYNTHETIC_PRIVATE_CANARY');canary.chmod(0o600)
id=uuid.uuid4().hex
assert rpc({'action':'deliver','id':id,'data':base64.b64encode(b'person,measure\np_fake,3\n').decode()})=={'ok':True}
folder=queue/id
assert (folder/'data.csv').stat().st_uid==u.pw_uid
(folder/'result.csv').symlink_to(canary)
assert 'error' in rpc({'action':'result','id':id})
(folder/'result.csv').unlink();os.mkfifo(folder/'result.csv')
assert 'error' in rpc({'action':'result','id':id})
(folder/'result.csv').unlink()
assert 'error' in rpc({'action':'run','command':'cat /var/lib/privacy-control/canary'})
assert canary.read_text()=='SYNTHETIC_PRIVATE_CANARY'
Path('/etc/privacy-assistant-guest.json').write_text(json.dumps({'role':'offline','queue':str(queue)}))
print(json.dumps({'firewall_live_check':True,'firewall_change_blocks':True,'unprivileged_delivery':True,'private_symlink_rejected':True,'fifo_rejected':True,'arbitrary_command_rejected':True}))
