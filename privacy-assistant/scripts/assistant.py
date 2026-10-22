"""One local front door. Never accepts raw data or a raw path from the Agent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/'skill'
sys.path.insert(0,str(CORE/'scripts'))
sys.path.insert(0,str(ROOT/'runtime/Lib/site-packages'))
VERSION='0.6.1'
AGENTS=('workbuddy','codex','claude')


def check_package(root=ROOT):
    from deidentify import safe_path,read_bytes
    safe_path(root)
    manifest=json.loads((root/'release.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=VERSION or not isinstance(manifest.get('files'),dict):raise ValueError('invalid_package')
    for rel,digest in manifest['files'].items():
        r=Path(rel)
        if r.is_absolute() or '..' in r.parts or '\\' in rel:raise ValueError('invalid_package')
        f=root/r
        if hashlib.sha256(read_bytes(f,64*1024*1024)).hexdigest()!=digest:raise ValueError('invalid_package')
    return manifest


def base_dir():
    if sys.platform=='win32':return Path(os.environ['LOCALAPPDATA'])/'LocalTablePrivacyAssistant'
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/LocalTablePrivacyAssistant'
    raise ValueError('local_desktop_required')


def initialise(base=None):
    from deidentify import safe_path
    base=base or base_dir();safe_path(base);base.mkdir(parents=True,exist_ok=True,mode=0o700)
    if sys.platform=='win32':
        from windows_host import restrict_acl
        restrict_acl(base)
    for name in ('Vault','Exchange','Settings'):
        p=base/name;safe_path(p);p.mkdir(exist_ok=True,mode=0o700)
    return base


def doctor():
    local=sys.platform in ('darwin','win32')
    report={'version':VERSION,'local_desktop':local,'installed_means_isolated':False,
      'raw_data_access_requested':False,'windows_device_validated':False,
      'current_agent_isolated':False,'table_wizard_available':sys.platform=='win32',
      'configuration_files_required_from_teacher':sys.platform!='win32'}
    if not local:report.update(status='blocked',code='local_desktop_required');return report
    try:check_package()
    except Exception:report.update(status='blocked',code='package_check_failed');return report
    try:import openpyxl;dependencies=openpyxl.__version__=='3.1.5'
    except Exception:dependencies=False
    report['table_runtime_ready']=dependencies
    if sys.platform=='win32':
        report['architecture_supported']=platform.machine().lower() in ('amd64','x86_64')
        report['backend']='persistent_virtual_machines'
        report['automatic_component_installation']=True
        ready=dependencies and report['architecture_supported']
    else:
        report['sandbox_installed']=Path('/usr/bin/sandbox-exec').is_file();ready=dependencies and report['sandbox_installed']
        report['cli_available']={a:shutil.which(a) is not None for a in ('codex','claude')}
        report['workbuddy_mac_isolation_supported']=False
    report.update(status='setup_ready' if ready else 'blocked',code='setup_ready' if ready else 'environment_not_ready')
    return report


def install(agent,base=None,skill_home=None):
    """Install a verified local launcher; no server/account/global security edits."""
    if agent not in AGENTS:raise ValueError('agent_invalid')
    manifest=check_package();base=initialise(base)
    from deidentify import safe_path
    app=base/'App'/VERSION
    safe_path(app)
    if app.exists():
        installed=check_package(app)
        if installed['files']!=manifest['files']:raise ValueError('version_conflict_preserved')
    else:
        app.parent.mkdir(exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix='.install-',dir=app.parent))
        try:
            for rel in manifest['files']:
                src=ROOT/rel;dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
            shutil.copy2(ROOT/'release.json',stage/'release.json');check_package(stage);stage.rename(app)
        finally:
            if stage.exists():shutil.rmtree(stage)
    settings=base/'Settings/preferences.json'
    safe_path(settings)
    settings.write_text(json.dumps({'version':VERSION,'agent':agent}),encoding='utf-8')
    # Discovery via a tiny skill, not by rewriting plugin registries or permissions.
    # WorkBuddy's official Upload Skill already installs its entry point.
    if agent in AGENTS:
        home=skill_home or (Path.home()/({'codex':'.agents','claude':'.claude','workbuddy':'.workbuddy'}[agent])/'skills')
        from deidentify import safe_path
        safe_path(home);home.mkdir(parents=True,exist_ok=True)
        dest=home/('privacy-assistant-launcher' if agent=='workbuddy' else 'privacy-assistant')
        safe_path(dest)
        marker=dest/'.privacy-assistant-managed'
        if dest.exists() and not marker.is_file():raise ValueError('existing_skill_preserved')
        dest.mkdir(exist_ok=True)
        safe_path(dest/'SKILL.md');safe_path(marker)
        content=(ROOT/'skills/start/SKILL.md').read_text(encoding='utf-8')
        if agent=='workbuddy':content=content.replace('name: privacy-assistant\n','name: privacy-assistant-launcher\n',1)
        content+='\n本机入口：`'+str(app/'scripts/auto_setup.py')+'`。此路径仅用于本地启动，不放进分享包。\n'
        (dest/'SKILL.md').write_text(content,encoding='utf-8');marker.write_text(VERSION)
    return {'status':'installed','version':VERSION,'agent':agent,'current_agent_isolated':False,'next':'打开隐私助手'}


def choose_agent(current):
    if sys.platform=='win32':
        ps=(ROOT/'scripts/launcher.ps1').read_text(encoding='utf-8-sig')
        import base64
        cmd=['powershell.exe','-NoProfile','-STA','-EncodedCommand',base64.b64encode(ps.encode('utf-16le')).decode()]
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=600)
        value=r.stdout.strip()
    else:
        script='''on run argv
set options to {"Codex 命令行", "Claude Code 命令行", "先试一次虚构演示"}
set selected to choose from list options with title "隐私助手" with prompt "打开新的受保护环境。当前聊天窗口不会因此被隔离。" default items {item 1 of options} OK button name "开始" cancel button name "取消"
if selected is false then return "cancel"
if item 1 of selected is item 1 of options then return "codex"
if item 1 of selected is item 2 of options then return "claude"
return "demo"
end run'''
        r=subprocess.run(['/usr/bin/osascript','-e',script],capture_output=True,text=True,timeout=600);value=r.stdout.strip()
    if value not in (*AGENTS,'demo','cancel','new','finish'):raise ValueError('selection_failed')
    return value


def notify(message):
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'隐私助手',0x40)
    elif sys.platform=='darwin':
        script='on run argv\ndisplay dialog (item 1 of argv) with title "隐私助手" buttons {"好"} default button "好"\nend run'
        subprocess.run(['/usr/bin/osascript','-e',script,message],capture_output=True)


def start(agent=None,show_ui=True,base=None):
    if sys.platform=='win32':
        import auto_setup
        return auto_setup.run(agent or 'workbuddy',True,base)
    info=doctor()
    if info['status']!='setup_ready':
        if show_ui:notify('本机暂不能建立所需隔离。Mac 需要本地命令行 Agent。请先用虚构材料，不能直接交给模型读取真实原表。')
        return info
    base=initialise(base)
    if show_ui:agent=choose_agent(agent)
    if agent=='cancel':return {'status':'cancelled','current_agent_isolated':False}
    if agent=='demo':
        if sys.platform=='win32':
            subprocess.Popen([sys.executable,'-I','-B',str(CORE/'scripts/windows_host.py'),'demo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            dest=base/'Vault'/('demo-'+__import__('uuid').uuid4().hex)
            r=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/python_entry.py'),str(CORE/'tests/make_demo.py'),str(dest)],capture_output=True,text=True,timeout=120)
            if r.returncode:raise ValueError('demo_failed')
            data=json.loads(r.stdout)
            if not data.get('all_checked_values_equal') or not data.get('derived_subset',{}).get('exact_identity_and_value_match'):raise ValueError('demo_failed')
            if show_ui:notify('虚构演示通过：60条整表和21条筛选结果回填准确。没有调用模型、没有上传真实数据。')
        return {'status':'demo_started' if sys.platform=='win32' else 'demo_passed','current_agent_isolated':False}
    if agent not in AGENTS:raise ValueError('agent_invalid')
    if agent=='workbuddy':return {'status':'blocked','code':'mac_workbuddy_gui_not_isolated','current_agent_isolated':False}
    binary=shutil.which(agent)
    if binary is None:return {'status':'blocked','code':'agent_not_installed','current_agent_isolated':False}
    import shlex
    args=[sys.executable,str(CORE/'scripts/agent_boundary.py'),'--vault',str(base/'Vault'),'--exchange',str(base/'Exchange'),'--',binary]
    if agent=='claude':args+=['--plugin-dir',str(ROOT)]
    # Open a new terminal, not an existing session. The command still enters the OS boundary.
    command=shlex.join(args)
    script='on run argv\ntell application "Terminal"\nactivate\ndo script (item 1 of argv)\nend tell\nend run'
    r=subprocess.run(['/usr/bin/osascript','-e',script,command],capture_output=True,text=True)
    if r.returncode:raise ValueError('terminal_open_failed')
    return {'status':'isolation_launcher_opened','runtime_isolation_verified':False,'current_agent_isolated':False}


def main():
    try:
        p=argparse.ArgumentParser();p.add_argument('action',choices=['doctor','install','start','setup','demo'],nargs='?',default='setup');p.add_argument('--agent',choices=AGENTS);p.add_argument('--no-ui',action='store_true');a=p.parse_args()
        if a.action=='doctor':result=doctor()
        elif a.action=='install':result=install(a.agent or ('workbuddy' if sys.platform=='win32' else 'codex'))
        elif a.action=='demo':result=start('demo',False)
        else:
            from auto_setup import run
            result=run(a.agent or ('workbuddy' if sys.platform=='win32' else 'codex'))
        print(json.dumps(result,ensure_ascii=False));return 2 if result['status']=='blocked' else 0
    except Exception:
        print(json.dumps({'status':'blocked','code':'assistant_not_ready','current_agent_isolated':False}));return 2

if __name__=='__main__':sys.exit(main())
