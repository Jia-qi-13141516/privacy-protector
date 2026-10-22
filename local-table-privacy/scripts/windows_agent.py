"""Online Agent VM: ONLY exchange is writable. Never map a raw-data directory."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import uuid
import xml.etree.ElementTree as ET


def configuration(exchange, bundle):
    root=ET.Element('Configuration')
    for k,v in [('Networking','Enable'),('ClipboardRedirection','Disable'),('AudioInput','Disable'),
                ('VideoInput','Disable'),('PrinterRedirection','Disable'),('vGPU','Disable')]:
        ET.SubElement(root,k).text=v
    folders=ET.SubElement(root,'MappedFolders')
    for host,guest,ro in [(exchange,r'C:\Exchange','false'),(bundle,r'C:\AgentKit','true')]:
        f=ET.SubElement(folders,'MappedFolder')
        for k,v in [('HostFolder',str(host)),('SandboxFolder',guest),('ReadOnly',ro)]:ET.SubElement(f,k).text=v
    ET.SubElement(ET.SubElement(root,'LogonCommand'),'Command').text=r'cmd.exe /c C:\AgentKit\start.cmd'
    return ET.tostring(root,encoding='unicode')


def stage_bundle(bundle, skill):
    # Never map the original kit directory: a user may have placed raw files there.
    bundle.mkdir()
    # Copy only release-manifest entries, never neighbors or user-added files.
    from deidentify import read_bytes, safe_path
    import hashlib
    entries=json.loads(read_bytes(skill/'package_manifest.json',1024*1024))
    for rel,digest in entries.items():
        r=Path(rel)
        if r.is_absolute() or '..' in r.parts:raise ValueError('package_path')
        data=read_bytes(skill/r,20*1024*1024)
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('package_changed')
        dest=bundle/'local-table-privacy'/r;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    shutil.copyfile(skill/'package_manifest.json',bundle/'local-table-privacy/package_manifest.json')
    ps=r'''$ErrorActionPreference = 'Stop'
# Use public DNS so blocking the NAT host does not silently disable DNS.
Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses '223.5.5.5','119.29.29.29' }
# Block LAN, host services and metadata endpoints while retaining public internet.
New-NetFirewallRule -DisplayName 'Privacy-BlockLocalIPv4' -Direction Outbound -Action Block -RemoteAddress '10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','127.0.0.0/8' | Out-Null
New-NetFirewallRule -DisplayName 'Privacy-BlockLocalIPv6' -Direction Outbound -Action Block -RemoteAddress '::1','fc00::/7','fe80::/10' | Out-Null
New-NetFirewallRule -DisplayName 'Privacy-BlockSMB' -Direction Outbound -Action Block -Protocol TCP -RemotePort 135,139,445 | Out-Null
New-NetFirewallRule -DisplayName 'Privacy-BlockSMBUDP' -Direction Outbound -Action Block -Protocol UDP -RemotePort 137,138 | Out-Null
if ((Get-NetFirewallProfile | Where-Object { -not $_.Enabled }).Count -gt 0) { throw 'Firewall disabled' }
Copy-Item 'C:\AgentKit\local-table-privacy' 'C:\Users\WDAGUtilityAccount\Desktop\local-table-privacy' -Recurse
Start-Process notepad.exe 'C:\AgentKit\使用说明.txt'
Start-Process explorer.exe 'C:\Exchange'
Start-Process 'https://www.workbuddy.cn/'
'''
    (bundle/'start.ps1').write_text(ps,encoding='utf-8-sig')
    import base64
    encoded=base64.b64encode(ps.encode('utf-16le')).decode('ascii')
    # EncodedCommand passes our fixed reviewed command without changing policy.
    (bundle/'start.cmd').write_text('@echo off\r\npowershell.exe -NoProfile -EncodedCommand '+encoded+'\r\nif errorlevel 1 (echo Boundary setup failed. Do not use real data. & pause)\r\n',encoding='ascii')
    (bundle/'使用说明.txt').write_text('仅在此沙盒内安装、登录并使用 WorkBuddy。技能在桌面的 local-table-privacy 文件夹；工作目录选 C:\\Exchange。\n原表、字段策略、任务密钥和实名结果不得复制进来。此窗口不能读取主机未映射文件；共享剪贴板已关闭。\n只放经本人审阅且允许交给模型的文件，代号数据仍需业务许可。不要连接主机远程控制、共享盘、内部 MCP 或真实学生知识库。\n关闭沙盒会清除软件及登录状态，先把成果保存到 C:\\Exchange。需回填时先关闭此沙盒，再从主机运行断网处理工具。\n若网络或登录失败，不要删除隔离限制。当前配置仍需在 Windows 实机验收。',encoding='utf-8-sig')


def main():
    if sys.platform!='win32':return 2
    msg=ctypes.windll.user32.MessageBoxW
    try:
        from windows_host import restrict_acl
        from deidentify import safe_path
        base=Path(os.environ['LOCALAPPDATA'])/'LocalTablePrivacyAgent';safe_path(base);base.mkdir(exist_ok=True);restrict_acl(base)
        exchange=base/'Exchange';exchange.mkdir(exist_ok=True)
        # Refuse links and reparse points; a clean, dedicated exchange only.
        from deidentify import safe_path
        safe_path(exchange)
        for f in exchange.rglob('*'):
            safe_path(f)
            if f.is_file() and f.stat().st_nlink!=1:raise ValueError('linked_file')
        if msg(None,'WorkBuddy 将在独立联网沙盒运行，只共享 Exchange 文件夹。请确认其中仅有允许提供给模型的资料，且原表没有复制在这里。此方式不会隔离主机上已经运行的 WorkBuddy。首次请只用虚构数据。继续？','隔离启动 WorkBuddy',0x24)!=6:return 2
        run=base/uuid.uuid4().hex;run.mkdir();bundle=run/'bundle'
        stage_bundle(bundle,Path(__file__).resolve().parents[1])
        wsb=run/'agent.wsb';wsb.write_text(configuration(exchange,bundle),encoding='utf-8')
        sandbox=Path(os.environ['SystemRoot'])/'System32/WindowsSandbox.exe'
        if not sandbox.is_file():raise ValueError('sandbox_missing')
        subprocess.Popen([str(sandbox),str(wsb)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return 0
    except Exception:
        msg(None,'隔离入口未成功启动。请检查 Windows 沙盒和权限；不要退回普通窗口处理真实原表。','本地表格隐私工具',0x10);return 2

if __name__=='__main__':sys.exit(main())
