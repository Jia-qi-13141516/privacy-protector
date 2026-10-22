"""Host controller: one task at a time; no raw data is printed or sent to an Agent."""
import ctypes,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from assistant import ROOT,CORE,initialise,check_package
sys.path.insert(0,str(CORE/'scripts'))
from windows_host import choose,configuration as offline_configuration
from windows_agent import configuration as agent_configuration,stage_bundle
from deidentify import safe_path,read_bytes,MAX_FILE


def guest_running():
    ps="if (Get-Process WindowsSandboxClient -ErrorAction SilentlyContinue) { [Console]::Write('RUNNING') }"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],capture_output=True,text=True)
    if r.returncode:raise ValueError('cannot_check_sandbox')
    return r.stdout.strip()=='RUNNING'


def agent(base,exchange):
    safe_path(exchange)
    for f in exchange.rglob('*'):
        safe_path(f)
        if f.is_file() and f.stat().st_nlink!=1:raise ValueError('linked_file')
    launch=base/'Settings'/('agent-'+uuid.uuid4().hex);launch.mkdir()
    stage_bundle(launch/'bundle',CORE)
    wsb=launch/'agent.wsb';wsb.write_text(agent_configuration(exchange,launch/'bundle'),encoding='utf-8')
    subprocess.Popen([str(Path(os.environ['SystemRoot'])/'System32/WindowsSandbox.exe'),str(wsb)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def main(mode):
    if sys.platform!='win32':return 2
    message=ctypes.windll.user32.MessageBoxW
    try:
        check_package();base=initialise()
        if guest_running():
            message(None,'请先保存并关闭正在使用的 Windows 沙盒，再从隐私助手继续。不会强制关闭你的窗口。','隐私助手',0x40);return 2
        active=base/'Settings/active.json'
        if mode=='new':
            original=choose('选择本地原表，不会加入聊天','*.xlsx;*.csv')
            task_id=uuid.uuid4().hex;task=base/'Vault'/task_id;task.mkdir();private=task/'private';private.mkdir()
            dest=private/('original'+original.suffix.lower());dest.write_bytes(read_bytes(original,MAX_FILE))
            active.write_text(json.dumps({'task':task_id}),encoding='utf-8')
        elif mode in ('finish','agent'):
            task_id=json.loads(active.read_text())['task']
            if len(task_id)!=32 or any(c not in '0123456789abcdef' for c in task_id):raise ValueError('bad_task')
            task=base/'Vault'/task_id;private=task/'private';safe_path(task)
        else:raise ValueError('bad_mode')
        exchange=base/'Exchange'/task_id;exchange.mkdir(exist_ok=True);safe_path(exchange)
        if mode=='agent':agent(base,exchange);return 0
        if mode=='finish':
            result=exchange/'结果.csv'
            if not result.is_file():result=choose('选择本次AI生成的结果CSV','*.csv')
            (private/'returned.csv').write_bytes(read_bytes(result,MAX_FILE))
        handoff=task/'handoff.json';handoff.unlink(missing_ok=True)
        control=task/'control';control.mkdir(exist_ok=True);(control/'request.json').write_text(json.dumps({'mode':mode}))
        mappings=[(ROOT/'runtime',r'C:\PrivacyRuntime',True),(CORE,r'C:\PrivacySkill',True),
          (ROOT/'scripts',r'C:\PrivacyUI',True),(control,r'C:\PrivacyControl',True),
          (task,r'C:\PrivacyTask',False),(exchange,r'C:\PrivacyExchange',False)]
        import xml.etree.ElementTree as ET
        xml=ET.fromstring(offline_configuration(mappings));xml.find('LogonCommand/Command').text=r'C:\PrivacyRuntime\python.exe -I -B C:\PrivacyUI\wizard_guest.py'
        wsb=task/'local.wsb';wsb.write_text(ET.tostring(xml,encoding='unicode'),encoding='utf-8')
        sandbox=Path(os.environ['SystemRoot'])/'System32/WindowsSandbox.exe'
        process=subprocess.Popen([str(sandbox),str(wsb)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        # Native wizard may take as long as the person needs; no data enters stdout.
        started=time.monotonic();deadline=started+7200;seen_guest=False
        while time.monotonic()<deadline:
            if handoff.exists():break
            running=guest_running();seen_guest=seen_guest or running
            if process.poll() not in (None,0) or (seen_guest and not running) or (not seen_guest and time.monotonic()-started>180):
                raise ValueError('guest_closed_without_result')
            time.sleep(2)
        else:raise ValueError('guest_timeout')
        result=json.loads(handoff.read_text(encoding='utf-8-sig'))
        for _ in range(60):
            if not guest_running():break
            time.sleep(1)
        else:message(None,'本地结果已保存。请关闭沙盒后，从助手继续；不会在原表窗口仍打开时启动联网AI。','隐私助手',0x40);return 2
        if result['status']=='ready_for_agent':agent(base,exchange)
        elif result['status']=='import_ready':
            folder=result['folder']
            if not folder.startswith('import-') or '/' in folder or '\\' in folder:raise ValueError('bad_output')
            subprocess.Popen(['explorer.exe',str(task/folder/'private')])
        elif result['status']=='cancelled':return 0
        else:message(None,'结果已保存在本地，没有交给AI。','隐私助手',0x40)
        return 0
    except Exception:
        message(None,'未能完成这一步。请先运行虚构演示或检查 Windows 沙盒，原表不会加入聊天，也不会退回普通窗口处理。','隐私助手',0x10);return 2

if __name__=='__main__':sys.exit(main(sys.argv[1]))
