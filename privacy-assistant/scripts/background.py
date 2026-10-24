"""Agent-facing background queue. Public replies contain status only, never material contents."""
import argparse,json,os,subprocess,sys,uuid,contextlib,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import task_channel as ch

ROOT=Path(__file__).resolve().parents[1]
ERRORS={'isolation_failed','runtime_integrity','local_runtime_unsupported','local_inference_failed',
 'local_inference_invalid','task_invalid','task_not_supported','numeric_invalid','active_content',
 'export_integrity','result_column_exists','source_changed','document_background_limit','document_paragraph_limit',
 'component_download_failed','download_source_rejected','download_integrity_failed','runtime_archive_invalid',
 'windows_x64_required','firmware_virtualization_disabled','restart_required','memory_below_requirement',
 'windows_version_unsupported','disk_space_insufficient','engine_install_not_completed','guest_install_timeout'}


def safe_error(error):
    from document_engine import ERROR_MESSAGES
    code=str(error)
    return code if code in ERRORS or code in ERROR_MESSAGES else 'local_task_failed'


def state(base,identifier,value=None):
    path=base/'Settings/BackgroundJobs'/(ch.task_id(identifier)+'.json')
    if value is not None:ch.put_json(path,dict(id=identifier,**value))
    return ch.get_json(path)


@contextlib.contextmanager
def runtime_lock(base):
    path=base/'Settings/background-runtime.lock';ch.regular(path)
    with path.open('a+b') as handle:
        if sys.platform=='win32':
            import msvcrt
            handle.write(b'0');handle.flush();handle.seek(0)
            end=time.monotonic()+3600
            while True:
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>end:raise ValueError('runtime_busy')
                    time.sleep(.5)
            try:yield
            finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)


def setup(base):
    path=base/'Settings/background-setup.json'
    try:
        def progress(stage,n,total):ch.put_json(path,{'phase':stage,'downloaded':n,'total':total})
        with runtime_lock(base):
            if sys.platform=='win32':
                from background_windows import prepare
                prepare(base,progress)
            elif sys.platform=='darwin':
                import local_runtime
                local_runtime.verify(local_runtime.install(base,progress=progress))
            else:raise ValueError('local_runtime_unsupported')
        ch.put_json(path,{'phase':'ready','data_processing':'local_offline','version':'0.9.0'})
    except Exception as error:ch.put_json(path,{'phase':'blocked','code':safe_error(error)})


def pick_file():
    if sys.platform=='darwin':
        from mac_workflow import dialog
        return Path(dialog('''set picked to choose file with prompt "选择要处理的文件；其内容只在本地处理。"
return POSIX path of picked'''))
    if sys.platform=='win32':
        from assistant import initialise
        from windows_service import dialogue
        r=dialogue(initialise(),{'mode':'any_file'})
        if r.get('cancelled'):raise ValueError('cancelled')
        return Path(r['path'])
    raise ValueError('local_runtime_unsupported')


def submit(base,source,instruction):
    if not isinstance(instruction,str) or not 1<=len(instruction)<=2000:raise ValueError('task_invalid')
    source=Path(source);ch.regular(source)
    if not source.is_file():raise ValueError('task_invalid')
    identifier=uuid.uuid4().hex;task=base/'Vault/Background'/identifier
    task.mkdir(parents=True,mode=0o700)
    ch.put_json(task/'request.json',{'source':str(source.resolve()),'instruction':instruction},True)
    state(base,identifier,{'phase':'queued'})
    options={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'stdin':subprocess.DEVNULL,'close_fds':True}
    if sys.platform=='win32':options['creationflags']=0x08000000
    else:options['start_new_session']=True
    child=subprocess.Popen([sys.executable,'-B',str(ROOT/'scripts/background.py'),'run','--id',identifier,'--base',str(base)],**options)
    return {'id':identifier,'phase':'queued','background_pid':child.pid}


def run(base,identifier):
    task=base/'Vault/Background'/ch.task_id(identifier)
    if (task/'.claimed').exists():return
    try:
        ch.write(task/'.claimed',b'claimed',True)
        request=ch.get_json(task/'request.json')
        state(base,identifier,{'phase':'preparing_runtime'})
        import local_runtime
        def progress(stage,n,total):state(base,identifier,{'phase':stage,'downloaded':n,'total':total})
        if sys.platform=='win32':
            from background_windows import execute
            with runtime_lock(base):reply=execute(base,task,request,progress)
        elif sys.platform=='darwin':
            with runtime_lock(base):config=local_runtime.install(base,progress=progress)
            ch.put_json(task/'request.json',dict(request,runtime=config))
            state(base,identifier,{'phase':'processing_offline'})
            # Deny local network and IPC bridges too, not just external HTTP.
            policy='(version 1)(allow default)(deny network*)(deny mach-lookup)(deny appleevent-send)'
            result=subprocess.run(['/usr/bin/sandbox-exec','-p',policy,sys.executable,'-B',str(ROOT/'scripts/background_worker.py'),str(task)],
                                  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3600,close_fds=True,
                                  env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG') if k in os.environ})
            try:reply=json.loads(result.stdout)
            except (ValueError,TypeError):raise ValueError('local_task_failed') from None
            if result.returncode or reply.get('phase')!='completed':raise ValueError(reply.get('code','local_task_failed'))
        else:raise ValueError('local_runtime_unsupported')
        public={k:reply[k] for k in ('kind','rows','input_rows','zero_match','paragraphs','entities','local_model_calls') if k in reply}
        name='result.xlsx' if reply['kind']=='table' else 'result.docx'
        state(base,identifier,{'phase':'completed','output':str(task/name),'cloud_data_sent':False,**public})
    except Exception as error:
        state(base,identifier,{'phase':'blocked','code':safe_error(error),'cloud_data_sent':False})


def main():
    try:
        import assistant
        parser=argparse.ArgumentParser();parser.add_argument('action',choices=['setup','submit','status','run']);parser.add_argument('--input');parser.add_argument('--task');parser.add_argument('--id');parser.add_argument('--base');args=parser.parse_args()
        assistant.check_package();os.umask(0o077);base=assistant.initialise(Path(args.base) if args.base else None)
        if args.action=='setup':setup(base);return 0
        if args.action=='submit':reply=submit(base,Path(args.input) if args.input else pick_file(),args.task)
        elif args.action=='status':reply=state(base,args.id)
        else:run(base,args.id);return 0
        print(json.dumps(reply,ensure_ascii=False));return 0
    except Exception as error:
        print(json.dumps({'phase':'blocked','code':safe_error(error),'cloud_data_sent':False}));return 2

if __name__=='__main__':sys.exit(main())
