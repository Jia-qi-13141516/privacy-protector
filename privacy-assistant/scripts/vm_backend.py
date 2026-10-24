"""Persistent VirtualBox backend. No shared folders, clipboard, or host RPC listener."""
import base64,json,os,platform,secrets,shutil,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from task_channel import read,write,get_json,put_json,regular,task_id
from component_download import fetch,digest
import vm_seed

ROOT=Path(__file__).resolve().parents[1]

def run(args,timeout=120):
    # No payload or raw stderr is ever returned to the Agent or placed in a log.
    p=subprocess.Popen([str(x) for x in args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    import threading
    result=[];overflow=[]
    def reader():
        size=0
        while True:
            block=p.stdout.read(65536)
            if not block:break
            size+=len(block)
            if size>48*1024*1024:overflow.append(True);p.kill();break
            result.append(block)
    thread=threading.Thread(target=reader,daemon=True);thread.start()
    try:code=p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:p.kill();p.wait();raise ValueError('component_timeout') from None
    finally:thread.join(timeout=10);p.stdout.close()
    if code or overflow:raise ValueError('component_command_failed')
    return b''.join(result).decode('utf-8',errors='strict')

def engine_path():
    if sys.platform=='win32':
        p=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Oracle/VirtualBox/VBoxManage.exe'
    else:p=Path(shutil.which('VBoxManage') or '/Applications/VirtualBox.app/Contents/MacOS/VBoxManage')
    regular(p)
    return p

def preflight(base):
    if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64'):
        raise ValueError('windows_x64_required')
    if sys.getwindowsversion().build<19041:raise ValueError('windows_version_unsupported')
    details=json.loads(run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        "$c=Get-CimInstance Win32_ComputerSystem; $p=Get-CimInstance Win32_Processor; @{memory=$c.TotalPhysicalMemory; hypervisor=$c.HypervisorPresent; virtualization=(@($p | Where-Object {$_.VirtualizationFirmwareEnabled}).Count -gt 0)} | ConvertTo-Json -Compress"]))
    if int(details['memory'])<7*1024**3:raise ValueError('memory_below_requirement')
    if not (details['hypervisor'] or details['virtualization']):raise ValueError('firmware_virtualization_disabled')
    statefile=base/'Settings/persistent-vm.json'
    state=get_json(statefile) if statefile.exists() else {}
    ready=all(state.get('machines',{}).get(role,{}).get('ready') for role in ('online','offline'))
    if shutil.disk_usage(base).free<(1 if ready else 12)*1024**3:raise ValueError('disk_space_insufficient')

def install_engine(base,progress):
    exe=engine_path()
    if exe.is_file():
        # Never alter a different existing hypervisor installation silently.
        version=run([exe,'--version']).strip()
        if not version.startswith('7.2.'):raise ValueError('existing_virtualbox_version_not_supported')
        return exe
    if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64'):raise ValueError('windows_x64_required')
    assets=get_json(ROOT/'backend/assets.json')['assets']
    lock=assets['virtualbox_windows']
    installer=fetch(lock,base/'Cache',lambda n,total:progress('正在下载隔离组件',n,total))
    runtime=fetch(assets['vc_redist'],base/'Cache',lambda n,total:progress('正在下载官方运行组件',n,total))
    # Launch only the pinned signed installer, not downloaded scripts.
    request=base/'Settings/install-engine.json';put_json(request,{'installer':str(installer),'sha256':lock['sha256'],'runtime':str(runtime),'runtime_sha256':assets['vc_redist']['sha256']})
    script=r'''param([string]$Request)
$ErrorActionPreference='Stop'
$r=Get-Content -LiteralPath $Request -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $r.runtime -Algorithm SHA256).Hash.ToLower() -ne $r.runtime_sha256) { exit 2 }
$s=Get-AuthenticodeSignature -LiteralPath $r.runtime
if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { exit 3 }
if ((Get-FileHash -LiteralPath $r.installer -Algorithm SHA256).Hash.ToLower() -ne $r.sha256) { exit 2 }
$s=Get-AuthenticodeSignature -LiteralPath $r.installer
if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Oracle') { exit 3 }
$v=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64' -ErrorAction SilentlyContinue
if (-not $v -or $v.Installed -ne 1 -or [version]$v.Version.TrimStart('v') -lt [version]'14.44.0.0') {
  $p=Start-Process -FilePath $r.runtime -ArgumentList '/install','/quiet','/norestart' -Verb RunAs -PassThru -Wait
  if ($p.ExitCode -eq 3010) { exit 10 }
  if ($p.ExitCode -ne 0) { exit 4 }
}
$p=Start-Process -FilePath $r.installer -ArgumentList '--silent','-msiparams','ADDLOCAL=VBoxApplication','REBOOT=ReallySuppress','VBOX_START=0','VBOX_INSTALLDESKTOPSHORTCUT=0','VBOX_REGISTERFILEEXTENSIONS=0' -Verb RunAs -PassThru -Wait
if ($p.ExitCode -eq 3010) { exit 10 }
if ($p.ExitCode -ne 0) { exit 4 }
'''
    ps=base/'Settings/install-engine.ps1';ps.write_text(script,encoding='utf-8-sig')
    command=base64.b64encode(('& {\n'+script+'\n} -Request '+"'"+str(request).replace("'","''")+"'").encode('utf-16le')).decode()
    # Execution policy is not changed; the encoded reviewed wrapper uses a signed vendor exe.
    result=subprocess.run(['powershell.exe','-NoProfile','-EncodedCommand',command],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if result.returncode==10:raise ValueError('restart_required')
    if result.returncode or not exe.is_file():raise ValueError('engine_install_not_completed')
    return exe

class Backend:
    def __init__(self,base,exe=None):
        self.base=base;self.exe=exe or engine_path();self.statefile=base/'Settings/persistent-vm.json'
        self.state=get_json(self.statefile) if self.statefile.exists() else {'version':1,'machines':{}}
        if self.state.get('version')!=1:raise ValueError('deployment_version_invalid')
    def save(self):put_json(self.statefile,self.state)
    def cli(self,*args,timeout=120):return run([self.exe,*args],timeout)
    def info(self,role):
        identifier=self.state['machines'][role]['id']
        if str(uuid.UUID(identifier))!=identifier:raise ValueError('invalid_vm_identity')
        text=self.cli('showvminfo',identifier,'--machinereadable')
        result={}
        for line in text.splitlines():
            if '=' in line:
                key,value=line.split('=',1);result[key]=value.strip('"')
        return result
    def boundary(self,role,allow_install_network=False):
        info=self.info(role)
        if any(k.startswith('SharedFolder') for k in info):raise ValueError('unexpected_shared_folder')
        if info.get('clipboard')!='disabled' or info.get('draganddrop')!='disabled':raise ValueError('clipboard_boundary_changed')
        if info.get('vrde')!='off' or info.get('usb')!='off':raise ValueError('device_boundary_changed')
        expected='nat' if role=='online' or allow_install_network else 'none'
        if info.get('nic1')!=expected:raise ValueError('network_boundary_changed')
        if any(info.get('nic'+str(n),'none')!='none' for n in range(2,9)):raise ValueError('network_boundary_changed')
        if role=='online' and info.get('localhostReachable')!='0':raise ValueError('host_loopback_exposed')
        if any('Forwarding' in k for k in info):raise ValueError('unexpected_port_forward')
        return info
    def credentials(self,role):
        return ['--username','root','--passwordfile',str(self.base/'Settings'/('vm-'+role+'.password'))]
    def enforce_idle_nat(self,role):
        if role!='online':return
        info=self.info(role)
        if info.get('VMState') in ('poweroff','aborted','saved'):
            # 7.2.22 can omit false from its XML and reload the default true.
            # Reapply the stricter setting before every boot; live checks still
            # reject changes in a running VM. Guest nftables independently denies host IPs.
            self.cli('modifyvm',self.state['machines'][role]['id'],'--nat-localhostreachable1','off')
    def guest(self,role,exe,args=(),timeout=120):
        return self.cli('guestcontrol',self.state['machines'][role]['id'],'run',*self.credentials(role),'--quiet','--exe',exe,'--timeout',str(timeout*1000),'--wait-stdout','--wait-stderr','--',*args,timeout=timeout+15)
    def rpc(self,role,request):
        self.boundary(role)
        identifier=uuid.uuid4().hex
        local=self.base/'Settings'/('request-'+identifier+'.json');put_json(local,request)
        if local.stat().st_size>45*1024*1024:local.unlink();raise ValueError('request_too_large')
        try:
            remote='/var/lib/privacy-control/'+identifier+'.json'
            self.cli('guestcontrol',self.state['machines'][role]['id'],'copyto',*self.credentials(role),str(local),remote)
            reply=json.loads(self.guest(role,'/usr/bin/python3',['-I','/opt/privacy-bridge/guest_rpc.py',identifier],timeout=3600 if request.get('action')=='background_task' else 120))
        finally:local.unlink(missing_ok=True)
        if not isinstance(reply,dict) or 'error' in reply:raise ValueError(reply.get('error','guest_response_invalid') if isinstance(reply,dict) else 'guest_response_invalid')
        return reply
    def start(self,role,visible=False):
        self.enforce_idle_nat(role)
        info=self.boundary(role)
        mode='separate' if visible else 'headless'
        if info.get('VMState')=='running':
            if role=='online':self.refresh_network()
            if visible:
                # Attaching a second viewer may report an existing GUI; never reset a running VM.
                try:self.cli('startvm',self.state['machines'][role]['id'],'--type','separate')
                except ValueError:
                    if self.info(role).get('VMState')!='running':raise
            return
        if info.get('VMState') not in ('poweroff','saved','aborted'):raise ValueError('vm_busy')
        self.cli('startvm',self.state['machines'][role]['id'],'--type',mode)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:
                self.rpc(role,{'action':'health'})
                if role=='online':self.refresh_network()
                return
            except ValueError:time.sleep(2)
        raise ValueError('vm_start_timeout')
    def refresh_network(self):
        import ipaddress
        if sys.platform!='win32':return
        text=run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Select-Object -ExpandProperty IPAddress) | ConvertTo-Json -Compress"])
        addresses=json.loads(text)
        if isinstance(addresses,str):addresses=[addresses]
        if not isinstance(addresses,list):raise ValueError('host_network_check_failed')
        addresses=sorted({str(ipaddress.IPv4Address(value)) for value in addresses})
        if self.state.get('host_addresses')!=addresses:
            self.rpc('online',{'action':'network','addresses':addresses})
            self.state['host_addresses']=addresses;self.save()
    def shutdown(self,role):
        identifier=self.state['machines'][role]['id']
        if self.info(role).get('VMState')=='poweroff':return
        self.cli('controlvm',identifier,'acpipowerbutton')
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.info(role).get('VMState')=='poweroff':return
            time.sleep(2)
        raise ValueError('vm_shutdown_pending')
    def provision(self,progress=lambda *args:None,roles=('offline','online')):
        if not roles or any(role not in ('offline','online') for role in roles):raise ValueError('invalid_role')
        if all(self.state['machines'].get(role,{}).get('ready') for role in roles):
            for role in roles:
                self.enforce_idle_nat(role);self.boundary(role)
            return self
        lock=get_json(ROOT/'backend/assets.json')['assets']
        disk=fetch(lock['ubuntu_disk'],self.base/'Cache',lambda n,total:progress('正在下载独立运行环境',n,total))
        for role in roles:
            progress('正在准备本地处理环境' if role=='offline' else '正在安装 WorkBuddy',0,0)
            entry=self.state['machines'].get(role)
            if entry and entry.get('ready'):
                self.enforce_idle_nat(role);self.boundary(role);continue
            if entry is None:
                identifier=str(uuid.uuid4());folder=self.base/'Machines'/role;regular(folder);folder.mkdir(parents=True,exist_ok=True)
                self.state['machines'][role]={'id':identifier,'folder':str(folder),'ready':False,'created':False};self.save()
            entry=self.state['machines'][role];identifier=entry['id'];folder=Path(entry['folder']);regular(folder)
            if folder!=self.base/'Machines'/role:raise ValueError('vm_location_changed')
            if not entry['created']:
                passwordfile=self.base/'Settings'/('vm-'+role+'.password')
                if not passwordfile.exists():write(passwordfile,secrets.token_urlsafe(36).encode(),True)
                if not (folder/'seed.iso').exists():vm_seed.create(ROOT,role,read(passwordfile).decode(),identifier,folder/'seed.iso')
                # UUID is reserved in the private journal before any side effect.
                try:self.info(role)
                except ValueError:self.cli('createvm','--name','PrivacyAssistant-'+role+'-'+identifier[:8],'--uuid',identifier,'--ostype','Ubuntu_64','--basefolder',str(folder),'--register')
                volume=folder/'system.vdi'
                if not volume.exists():self.cli('clonemedium','disk',str(disk),str(volume),'--format','VDI',timeout=600)
                self.cli('showmediuminfo','disk',str(volume))
                self.cli('modifymedium','disk',str(volume),'--resize','30720' if role=='online' else '10240')
                self.cli('modifyvm',identifier,'--memory','3072','--cpus','2','--graphicscontroller','vmsvga','--vram','128','--nic1','nat','--nic2','none','--clipboard-mode','disabled','--draganddrop','disabled','--audio-enabled','off','--usb-ohci','off','--usb-ehci','off','--usb-xhci','off','--vrde','off','--nat-localhostreachable1','off','--boot1','disk','--boot2','none','--boot3','none','--boot4','none')
                if 'SATA' not in self.info(role).values():self.cli('storagectl',identifier,'--name','SATA','--add','sata','--controller','IntelAhci')
                self.cli('storageattach',identifier,'--storagectl','SATA','--port','0','--device','0','--type','hdd','--medium',str(volume))
                self.cli('storageattach',identifier,'--storagectl','SATA','--port','1','--device','0','--type','dvddrive','--medium',str(folder/'seed.iso'))
                entry['created']=True;self.save()
            if not entry.get('guest_installed'):
                self.boundary(role,True)
                if self.info(role).get('VMState')!='running':self.cli('startvm',identifier,'--type','headless')
                deadline=time.monotonic()+3600
                while time.monotonic()<deadline:
                    try:
                        self.guest(role,'/usr/bin/test',['-f','/var/lib/privacy-install/ready.json'],timeout=15);break
                    except ValueError:time.sleep(5)
                else:raise ValueError('guest_install_timeout')
                entry['guest_installed']=True;self.save()
            self.shutdown(role)
            self.cli('storageattach',identifier,'--storagectl','SATA','--port','1','--device','0','--type','dvddrive','--medium','none')
            if role=='offline':self.cli('modifyvm',identifier,'--nic1','none')
            # Remove bootstrap credentials from the guest's mounted installation media.
            (folder/'seed.iso').unlink(missing_ok=True)
            entry['ready']=True;self.save();self.start(role)
            if self.rpc(role,{'action':'health'})['status']!=role:raise ValueError('guest_health_failed')
        return self
