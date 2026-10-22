"""Windows-only GUI launcher; input files are selected, never opened by this host."""
import ctypes
from ctypes import wintypes as W
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import uuid
import xml.etree.ElementTree as ET


def restrict_acl(base):
    sid=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True).stdout
    import csv,io,re
    sid=next(csv.reader(io.StringIO(sid)))[1]
    if re.fullmatch(r'S-1-5-[0-9-]+',sid) is None:raise ValueError('acl')
    subprocess.run(['icacls',str(base),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True,check=True)


def stage_selected(path, dest, job=False):
    from deidentify import safe_path, read_bytes, MAX_FILE
    safe_path(path);dest.mkdir()
    if not job:
        (dest/path.name).write_bytes(read_bytes(path,MAX_FILE))
        return path.name
    private=path.parent/'private';safe_path(private)
    binding=json.loads(read_bytes(private/'job.json',1024*1024))
    import re
    names=list(binding['tables'])
    if not all(isinstance(n,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,31}',n) for n in names):raise ValueError('invalid_job')
    (dest/'private').mkdir()
    for name in ['job.json','job-key.bin']+[n+'.csv' for n in names]:
        (dest/'private'/name).write_bytes(read_bytes(private/name,MAX_FILE))
    return None


def choose(title, pattern):
    class OPENFILENAMEW(ctypes.Structure):
        _fields_=[('lStructSize',W.DWORD),('hwndOwner',W.HWND),('hInstance',W.HINSTANCE),('lpstrFilter',W.LPCWSTR),('lpstrCustomFilter',W.LPWSTR),('nMaxCustFilter',W.DWORD),('nFilterIndex',W.DWORD),('lpstrFile',W.LPWSTR),('nMaxFile',W.DWORD),('lpstrFileTitle',W.LPWSTR),('nMaxFileTitle',W.DWORD),('lpstrInitialDir',W.LPCWSTR),('lpstrTitle',W.LPCWSTR),('Flags',W.DWORD),('nFileOffset',W.WORD),('nFileExtension',W.WORD),('lpstrDefExt',W.LPCWSTR),('lCustData',W.LPARAM),('lpfnHook',ctypes.c_void_p),('lpTemplateName',W.LPCWSTR),('pvReserved',ctypes.c_void_p),('dwReserved',W.DWORD),('FlagsEx',W.DWORD)]
    buf=ctypes.create_unicode_buffer(32768);args=OPENFILENAMEW()
    args.lStructSize=ctypes.sizeof(args);args.lpstrFilter='所需文件\0'+pattern+'\0\0';args.lpstrFile=ctypes.cast(buf,W.LPWSTR);args.nMaxFile=len(buf);args.lpstrTitle=title;args.Flags=0x1000|0x800|0x8
    if not ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(args)):raise ValueError('cancelled')
    p=Path(buf.value)
    if not p.is_absolute() or p.is_symlink() or str(p).startswith('\\\\'):raise ValueError('local_file_required')
    return p


def configuration(mappings):
    root=ET.Element('Configuration')
    for name in ['Networking','ClipboardRedirection','AudioInput','VideoInput','PrinterRedirection','vGPU']:
        ET.SubElement(root,name).text='Disable'
    folders=ET.SubElement(root,'MappedFolders')
    for host,guest,readonly in mappings:
        f=ET.SubElement(folders,'MappedFolder');ET.SubElement(f,'HostFolder').text=str(host);ET.SubElement(f,'SandboxFolder').text=guest;ET.SubElement(f,'ReadOnly').text='true' if readonly else 'false'
    logon=ET.SubElement(root,'LogonCommand')
    ET.SubElement(logon,'Command').text='C:\\PrivacyRuntime\\python.exe -I -B C:\\PrivacyCode\\windows_guest.py'
    return ET.tostring(root,encoding='unicode')


def main():
    if sys.platform!='win32':return 2
    msg=ctypes.windll.user32.MessageBoxW
    try:
        # The portable kit contains only runtime, source and documentation.
        kit=Path(__file__).resolve().parents[2]
        runtime=kit/'runtime'
        sandbox=Path(os.environ['SystemRoot'])/'System32/WindowsSandbox.exe'
        if not sandbox.is_file() or not (runtime/'python.exe').is_file():
            msg(None,'需要启用 Windows 沙盒，并使用包含 runtime 的完整工具包。请先查看使用说明；不能改为直接读取真实资料。','本地表格隐私工具',0x10);return 2
        mode=sys.argv[1] if len(sys.argv)==2 else 'demo'
        if mode not in ('demo','deidentify','prepare-import','prepare-summary'):return 2
        if mode!='demo' and msg(None,'请先在这台电脑完成虚构演示，并由信息技术人员验收。真实文件须已获授权，位于非云同步目录，且不要让 WorkBuddy、索引软件或屏幕共享读取。是否已完成这些准备？','真实资料使用前',0x24)!=6:return 2
        base=Path(os.environ['LOCALAPPDATA'])/'LocalTablePrivacy'
        # Restrict to this Windows account and SYSTEM; chmod alone is not a Windows ACL.
        from deidentify import safe_path
        safe_path(base);base.mkdir(exist_ok=True)
        restrict_acl(base)
        run=base/uuid.uuid4().hex;run.mkdir();control=run/'control';control.mkdir();output=run/'output';output.mkdir()
        mappings=[(runtime,r'C:\PrivacyRuntime',True),(kit/'skill',r'C:\PrivacySkill',True),(Path(__file__).parent,r'C:\PrivacyCode',True),(control,r'C:\PrivacyControl',True),(output,r'C:\PrivacyOutput',False)]
        config={'mode':mode}
        fields=[] if mode=='demo' else [('input','选择本地原表（不会上传）','*.xlsx;*.csv'),('policy','选择本地字段策略','*.json')]
        if mode=='prepare-import':fields += [('job','选择本次脱敏任务的 receipt.json','receipt.json'),('results','选择处理后的代号结果表','*.csv'),('import_policy','选择本地导入字段策略','*.json')]
        if mode=='prepare-summary':fields += [('job','选择本次脱敏任务的 receipt.json','receipt.json'),('summary_policy','选择本地汇总策略','*.json')]
        for i,(key,title,pattern) in enumerate(fields):
            p=choose(title,pattern);guest=rf'C:\PrivacyInput{i}'
            staged=run/('input'+str(i));name=stage_selected(p,staged,job=key=='job')
            mappings.append((staged,guest,True));config[key]=guest if key=='job' else guest+'\\'+name
        (control/'request.json').write_text(json.dumps(config),encoding='utf-8')
        wsb=run/'local-privacy.wsb';wsb.write_text(configuration(mappings),encoding='utf-8')
        subprocess.Popen([str(sandbox),str(wsb)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        msg(None,'已打开本地处理沙盒；仅沙盒断网，WorkBuddy和浏览器可继续联网。处理后查看本地结果。待审阅汇总须本人检查后再决定是否提供给AI，原表与身份明细不进入对话。','本地表格隐私工具',0x40)
        subprocess.Popen(['explorer.exe',str(output)])
        return 0
    except Exception:
        msg(None,'已取消或环境检查未通过。没有将原表发送给模型。请检查沙盒、权限和配套说明；不显示原始内容或详细异常。','本地表格隐私工具',0x10);return 2


if __name__=='__main__':sys.exit(main())
