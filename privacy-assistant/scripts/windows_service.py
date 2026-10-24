"""Private host controller. Its UI owns file choice and identity confirmation."""
import base64,ctypes,json,os,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from assistant import ROOT,initialise,check_package,notify
from task_channel import Jobs,task_id,read,write,put_json,get_json,decode_blob
from vm_backend import Backend,install_engine,preflight

def dialogue(base,request):
    folder=base/'Vault/UI'/uuid.uuid4().hex;folder.mkdir(parents=True,mode=0o700)
    incoming=folder/'request.json';outgoing=folder/'reply.json';put_json(incoming,request)
    source=(ROOT/'backend/dialog.ps1').read_text(encoding='utf-8-sig')
    def quoted(path):return "'"+str(path).replace("'","''")+"'"
    script='& {\n'+source+'\n} -InputPath '+quoted(incoming)+' -OutputPath '+quoted(outgoing)
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-STA','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode:raise ValueError('local_window_failed')
        return get_json(outgoing,1024*1024)
    finally:
        incoming.unlink(missing_ok=True);outgoing.unlink(missing_ok=True);folder.rmdir()

def register_startup(base):
    import winreg
    # Only this user's startup entry, never another Agent's preferences or account.
    command=subprocess.list2cmdline([sys.executable,'-I','-B',str(ROOT/'scripts/windows_service.py'),'--background'])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        winreg.SetValueEx(key,'LocalPrivacyAssistant',0,winreg.REG_SZ,command)

def progress(base,label,done=0,total=0):
    put_json(base/'Settings/install-progress.json',{'stage':label,'downloaded':done,'total':total})

def show_progress(base):
    source=(ROOT/'backend/progress.ps1').read_text(encoding='utf-8-sig')
    path=str(base/'Settings/install-progress.json').replace("'","''")
    script='& {\n'+source+"\n} -StatusPath '"+path+"'"
    subprocess.Popen(['powershell.exe','-NoProfile','-STA','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)

def safe_source(path,document=False):
    # Accept a local fixed drive only. No mapped network or cloud retrieval here.
    if path.suffix.lower() not in (('.txt','.md','.docx','.pdf') if document else ('.xlsx','.csv')) or str(path).startswith('\\\\'):raise ValueError('local_table_required')
    drive=ctypes.windll.kernel32.GetDriveTypeW
    drive.argtypes=[ctypes.c_wchar_p];drive.restype=ctypes.c_uint
    if drive(path.anchor)!=3:raise ValueError('local_table_required')
    return read(path,5*1024*1024 if document else 20*1024*1024)

def handle(base,backend,jobs,request):
    backend.refresh_network()
    if backend.rpc('online',{'action':'health'}).get('status')!='online':raise ValueError('boundary_changed')
    identifier=task_id(request['id']);action=request['action']
    if action=='new_document' or (action=='submit_result' and jobs.kind(identifier)=='document'):
        from document_windows import handle as document_handle
        document_handle(base,backend,jobs,request,dialogue,safe_source)
        backend.rpc('online',{'action':'ack','id':identifier});return
    if action=='new_table':
        if jobs.path(identifier).exists():
            backend.rpc('online',{'action':'ack','id':identifier});return
        jobs.create(identifier)
        selected=dialogue(base,{'mode':'file'})
        if selected.get('cancelled'):jobs.advance(identifier,'cancel');backend.rpc('online',{'action':'status','id':identifier,'phase':'cancelled'});return
        source=Path(selected['path']);data=safe_source(source)
        jobs.advance(identifier,'selected');backend.start('offline')
        schema=backend.rpc('offline',{'action':'input','id':identifier,'extension':source.suffix.lower(),'data':base64.b64encode(data).decode()})['schema']
        del data,source,selected
        fields=dialogue(base,{'mode':'fields','fields':schema['fields']})
        if fields.get('cancelled'):jobs.advance(identifier,'cancel');backend.rpc('online',{'action':'status','id':identifier,'phase':'cancelled'});return
        approved=backend.rpc('offline',{'action':'prepare','id':identifier,'choices':fields['choices']})
        backend.refresh_network()
        if backend.rpc('online',{'action':'health'}).get('status')!='online':raise ValueError('boundary_changed')
        backend.rpc('online',{'action':'deliver','id':identifier,'data':approved['data'],'columns':approved['columns']})
        jobs.advance(identifier,'released')
    elif action=='submit_result':
        if jobs.phase(identifier)!='ready_for_agent':raise ValueError('task_not_ready')
        result=backend.rpc('online',{'action':'result','id':identifier})
        backend.start('offline');preview=backend.rpc('offline',{'action':'preview','id':identifier,'data':result['data']})
        jobs.advance(identifier,'result_received')
        backend.rpc('online',{'action':'status','id':identifier,'phase':'waiting_for_confirmation'})
        confirmation=dialogue(base,{'mode':'preview','rows':preview['preview']})
        if not confirmation.get('confirmed'):jobs.advance(identifier,'cancel');backend.rpc('online',{'action':'status','id':identifier,'phase':'cancelled'});return
        result=backend.rpc('offline',{'action':'export','id':identifier})
        folder=base/'Vault/Exports';folder.mkdir(exist_ok=True)
        write(folder/(identifier+'.xlsx'),decode_blob(result['xlsx']),exclusive=True)
        jobs.advance(identifier,'local_confirmed')
        backend.rpc('online',{'action':'status','id':identifier,'phase':'completed'})
        subprocess.Popen(['explorer.exe',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:raise ValueError('invalid_request')
    backend.rpc('online',{'action':'ack','id':identifier})

def launch(base):
    # The short Agent-facing entry returns no file names, rows, credentials or logs.
    put_json(base/'Settings/show-window.json',{'show':True})
    subprocess.Popen([sys.executable,'-I','-B',str(ROOT/'scripts/windows_service.py')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    return {'status':'automatic_installation_started','current_agent_isolated':False}

def main():
    if sys.platform!='win32':return 2
    check_package();base=initialise()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    mutex=kernel.CreateMutexW(None,True,'Local\\PrivacyAssistantPersistentV1')
    if not mutex:return 2
    if ctypes.get_last_error()==183:kernel.CloseHandle(mutex);return 0
    try:
        progress(base,'正在检查已有环境')
        show_progress(base)
        callback=lambda label,done=0,total=0:progress(base,label,done,total)
        preflight(base)
        register_startup(base)
        backend=Backend(base,install_engine(base,callback));backend.provision(callback)
        from bridge_bundle import update
        update(backend,ROOT)
        from vm_acceptance import verify
        verify(backend)
        progress(base,'安装完成')
        put_json(base/'Settings/automatic-setup.json',{'status':'local_runtime_ready','version':1,'isolation_checked':True,'profile_storage_persistent':True,'current_agent_isolated':False})
        jobs=Jobs(base/'Settings/Jobs')
        while True:
            show=base/'Settings/show-window.json'
            if show.exists():show.unlink();backend.start('online',visible=True)
            try:
                if backend.info('online').get('VMState')!='running':time.sleep(2);continue
                request=backend.rpc('online',{'action':'poll'})['request']
                if request:
                    try:handle(base,backend,jobs,request)
                    except Exception as error:
                        identifier=task_id(request['id'])
                        try:jobs.advance(identifier,'block')
                        except Exception:pass
                        backend.rpc('online',{'action':'status','id':identifier,'phase':'blocked'})
                        from document_engine import ERROR_MESSAGES
                        notify(ERROR_MESSAGES.get(str(error),'这一步未能通过保护检查，未提供新的原始内容。请检查文件格式、脱敏预览和结果代号；不要改用普通聊天上传原件。'))
                    finally:backend.rpc('online',{'action':'ack','id':request['id']})
            except Exception:
                # Never reconnect a changed boundary by weakening its settings.
                progress(base,'保护检查未通过，已暂停处理')
                time.sleep(5)
            time.sleep(2)
    except Exception as error:
        messages={
          'restart_required':'需要重新启动电脑，登录后会自动继续安装。',
          'windows_x64_required':'本安装包需要 Windows x64 电脑。当前设备不能启用这套隔离环境。',
          'windows_version_unsupported':'需要 Windows 10 2004 或更新版本。保护尚未启用。',
          'memory_below_requirement':'这套独立运行环境需要至少 8 GB 内存。当前电脑暂不能启用。',
          'disk_space_insufficient':'请为隐私助手所在磁盘留出至少 12 GB 可用空间，再打开隐私助手继续。',
          'firmware_virtualization_disabled':'电脑的硬件虚拟化尚未开启。软件不能代替你修改 BIOS；当前不会接收原表。',
          'existing_virtualbox_version_not_supported':'检测到已有的其他版本 VirtualBox。为保留你原有环境，本次未覆盖安装；当前不会接收原表。',
        }
        code=str(error) if str(error) in (*messages,'guest_install_timeout','component_download_failed','engine_install_not_completed') else 'installation_not_completed'
        put_json(base/'Settings/automatic-setup.json',{'status':'blocked','code':code,'current_agent_isolated':False})
        progress(base,'安装未完成')
        notify(messages.get(code,'安装尚未完成，保护没有启用。再次打开隐私助手会重试，并保留已有环境和登录资料。'))
        return 2
    finally:
        kernel.ReleaseMutex(mutex);kernel.CloseHandle(mutex)

if __name__=='__main__':sys.exit(main())
