"""Generate a private NoCloud seed; never return generated credentials to an Agent."""
import base64,io,json
from pathlib import Path

from network_policy import firewall

def config(root,role,password,instance_id):
    if role not in ('online','offline'):raise ValueError('invalid_role')
    writes=[]
    def add(path,data,permissions='0644'):
        if isinstance(data,str):data=data.encode()
        writes.append({'path':path,'owner':'root:root','permissions':permissions,'encoding':'b64','content':base64.b64encode(data).decode()})
    for name in ('task_channel.py','guest_client.py','table_wizard.py','network_policy.py'):
        add('/opt/privacy-bridge/'+name,(root/'scripts'/name).read_bytes())
    for name in ('guest_rpc.py','guest_health.py','acceptance_guest.py','setup_guest.sh','guest_skill.md'):
        add('/opt/privacy-bridge/'+name,(root/'backend'/name).read_bytes(),'0755' if name.endswith('.sh') else '0644')
    add('/opt/skill/scripts/deidentify.py',(root/'skill/scripts/deidentify.py').read_bytes())
    add('/etc/privacy-assistant-guest.json',json.dumps({'role':role,'queue':'/home/teacher/PrivacyTasks'}))
    add('/etc/nftables.conf',firewall())
    unit='[Unit]\nDescription=Privacy assistant first-time setup\nAfter=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=0\nConditionPathExists=!/var/lib/privacy-install/ready.json\n[Service]\nType=oneshot\nExecStart=/bin/sh /opt/privacy-bridge/setup_guest.sh '+role+'\nRestart=on-failure\nRestartSec=30\nTimeoutStartSec=0\n[Install]\nWantedBy=multi-user.target\n'
    add('/etc/systemd/system/privacy-install.service',unit)
    asset=json.loads((root/'backend/assets.json').read_text())['assets']['workbuddy']
    # Trusted URL and digest are embedded at build time; no downloaded shell code.
    downloader='''import hashlib,urllib.request
from pathlib import Path
url=URL
expected=SHA
destination=Path('/var/lib/privacy-install/workbuddy.deb')
h=hashlib.sha256();count=0
with urllib.request.urlopen(url,timeout=60) as response,destination.open('wb') as out:
 if not response.geturl().startswith('https://download.codebuddy.cn/workbuddy/'):raise RuntimeError('source')
 while True:
  block=response.read(1048576)
  if not block:break
  count+=len(block)
  if count>600000000:raise RuntimeError('limit')
  out.write(block);h.update(block)
if h.hexdigest()!=expected:
 destination.unlink();raise RuntimeError('integrity')
'''.replace('URL',repr(asset['url'])).replace('SHA',repr(asset['sha256']))
    add('/opt/privacy-bridge/fetch_workbuddy.py',downloader)
    users=[{'name':'teacher','uid':1000,'groups':['users'],'shell':'/bin/bash','lock_passwd':True}]
    return {'hostname':'privacy-'+role,'manage_etc_hosts':True,'locale':'zh_CN.UTF-8','timezone':'Asia/Shanghai','users':users,'disable_root':False,
            'ssh_pwauth':False,'chpasswd':{'expire':False,'users':[{'name':'root','password':password,'type':'text'}]},
            'write_files':writes,'runcmd':[['systemctl','daemon-reload'],['systemctl','enable','--now','--no-block','privacy-install.service']],
            'final_message':'Privacy component initialization finished'}

def create(root,role,password,instance_id,destination):
    import pycdlib
    data={'user-data':('#cloud-config\n'+json.dumps(config(root,role,password,instance_id))).encode(),
          'meta-data':json.dumps({'instance-id':instance_id,'local-hostname':'privacy-'+role}).encode(),
          'network-config':json.dumps({'version':2,'ethernets':{'privacy':{'match':{'name':'en*'},'dhcp4':True,'dhcp4-overrides':{'use-dns':False},'nameservers':{'addresses':['223.5.5.5','119.29.29.29']}}}}).encode()}
    iso=pycdlib.PyCdlib();iso.new(interchange_level=3,joliet=3,vol_ident='cidata')
    streams=[]
    for i,(name,content) in enumerate(data.items()):
        stream=io.BytesIO(content);streams.append(stream)
        iso.add_fp(stream,len(content),iso_path='/'+['USERDATA.;1','METADATA.;1','NETWORK.;1'][i],joliet_path='/'+name)
    iso.write(str(destination));iso.close()
