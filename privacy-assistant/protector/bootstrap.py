"""One Agent-facing installer. Background services persist; no account transfer."""
import argparse,base64,hashlib,json,os,platform,shlex,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from install_common import VERSION,install_plan,qualification,verify_tree
import client
ROOT=Path(__file__).resolve().parents[1]

def identity():
    if sys.platform=='darwin':
        if os.geteuid()==0:raise ValueError('agent_is_privileged')
        return os.getuid()
    if sys.platform=='win32':
        from windows_native import current_sid
        from install_windows import elevated
        if elevated():raise ValueError('agent_is_privileged')
        return current_sid()
    raise ValueError('unsupported_platform')

def install_launcher(agent,app):
    homes={'codex':'.agents','claude':'.claude','workbuddy':'.codebuddy'}
    dest=Path.home()/homes[agent]/'skills/privacy-protector'
    for p in (dest,*dest.parents):
        if p.is_symlink():raise ValueError('existing_skill_preserved')
    marker=dest/'.privacy-protector-managed'
    if dest.exists() and not marker.is_file():raise ValueError('existing_skill_preserved')
    dest.mkdir(parents=True,exist_ok=True)
    text=(app/'skills/start/SKILL.md').read_text(encoding='utf-8')
    text+='\n本机受保护入口：`'+str(app/'protector/client.py')+'`。仅用于这台电脑，不放入分享包。\n'
    (dest/'SKILL.md').write_text(text,encoding='utf-8');marker.write_text(VERSION)
    # Only replace launchers created by our earlier installer. Never remove a
    # user's unrelated/custom skills or touch their client authentication files.
    for name in ('privacy-assistant','privacy-assistant-launcher'):
        old=dest.parent/name
        if (old/'.privacy-assistant-managed').is_file() and not old.is_symlink():
            (old/'SKILL.md').write_text(text,encoding='utf-8')

def run(agent,plan_only=False):
    if agent not in ('codex','claude','workbuddy'):raise ValueError('agent_invalid')
    who=identity();plan=install_plan(sys.platform,who,platform.machine())
    if plan_only:return dict(plan,operation='plan_only',installed=False)
    qualification(ROOT);verify_tree(ROOT)
    app=Path(plan['app'])
    try:health=client.request({'action':'health'})
    except Exception:health=None
    reused=health is not None
    if health is None:
        digest=hashlib.sha256((ROOT/'release.json').read_bytes()).hexdigest()
        if sys.platform=='darwin':
            executable=ROOT/plan['python']
            args=[str(executable),'-I','-B',str(ROOT/'protector/install_mac.py'),'--source',str(ROOT),'--uid',str(who),'--gid',str(os.getgid()),'--manifest-sha',digest]
            script='on run argv\ndo shell script (item 1 of argv) with administrator privileges\nend run'
            p=subprocess.run(['/usr/bin/osascript','-e',script,shlex.join(args)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        else:
            # UAC is the single system authorization. No password is collected,
            # stored or copied, and it cannot be bypassed by a Skill.
            executable=ROOT/'runtime/python.exe'
            arguments=subprocess.list2cmdline(['-I','-B',str(ROOT/'protector/install_windows.py'),'--source',str(ROOT),'--sid',who,'--manifest-sha',digest])
            def quote(value):return "'"+value.replace("'","''")+"'"
            code='$p=Start-Process -FilePath '+quote(str(executable))+' -ArgumentList '+quote(arguments)+' -Verb RunAs -Wait -PassThru; exit $p.ExitCode'
            encoded=base64.b64encode(code.encode('utf-16le')).decode()
            p=subprocess.run(['powershell.exe','-NoProfile','-EncodedCommand',encoded],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if p.returncode:raise ValueError('system_authorization_or_install_failed')
    # Installation starts a persistent service; querying it never starts a
    # weaker worker, re-installs the client, or creates another online login.
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        try:
            health=client.request({'action':'health'});install_launcher(agent,app)
            return dict(health,account_files_modified=False,installation_reused=reused)
        except Exception:time.sleep(1)
    raise ValueError('service_start_pending')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--agent',choices=['codex','claude','workbuddy'],required=True);parser.add_argument('--plan',action='store_true');a=parser.parse_args()
    try:r=run(a.agent,a.plan)
    except Exception as e:r={'ready':False,'phase':'blocked','code':str(e) if str(e) in ('agent_is_privileged','platform_validation_pending','unsupported_platform','windows_x64_required','service_start_pending','system_authorization_or_install_failed','existing_skill_preserved') else 'installation_failed'}
    print(json.dumps(r,ensure_ascii=False));sys.exit(2 if r.get('phase')=='blocked' else 0)
