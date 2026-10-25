"""Agent-facing background queue. Public replies contain status only, never material contents."""
import argparse,json,os,subprocess,sys,uuid,contextlib,time,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import task_channel as ch
import performance

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
    return code if code in ERRORS or code in ERROR_MESSAGES or code in performance.ERROR_MESSAGES else 'local_task_failed'


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


def blocked(error):
    code=safe_error(error)
    return {'phase':'blocked','code':code,'message':performance.ERROR_MESSAGES.get(code,'本地处理未完成，已停止；没有上传原件或降低隐私保护。'),'cloud_data_sent':False}


def run_mac_worker(task,self_test=False):
    # Keep the same OS boundary for tests and real material; no alternate online path.
    policy='(version 1)(allow default)(deny network*)(deny mach-lookup)(deny appleevent-send)'
    process=subprocess.Popen(['/usr/bin/sandbox-exec','-p',policy,sys.executable,'-B',str(ROOT/'scripts/background_worker.py'),str(task)],
                             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,
                             env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG') if k in os.environ})
    deadline=time.monotonic()+(200 if self_test else 3600)
    try:
        while True:
            try:
                output,_=process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    try:performance.guard_worker(process.pid)
                    except ValueError as error:
                        if str(error)!='memory_monitor_unavailable' or process.poll() is None:raise
                if time.monotonic()>deadline:raise ValueError('self_test_slow' if self_test else 'inference_timeout')
    except Exception:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.communicate()
        raise
    try:reply=json.loads(output)
    except (ValueError,TypeError):raise ValueError('local_task_failed') from None
    if process.returncode or reply.get('phase')!='completed':raise ValueError(reply.get('code','local_task_failed'))
    return reply


def ensure_ready(base,progress):
    # Caller holds runtime_lock across readiness and the full task, so model jobs cannot overlap.
    import self_check,local_runtime,hashlib
    info=performance.hardware()
    if sys.platform=='win32':
        from background_windows import prepare
        runtime=prepare(base,progress)
    elif sys.platform=='darwin':
        performance.require_capacity(info)
        runtime=local_runtime.install(base,progress=progress);local_runtime.verify(runtime)
    else:raise ValueError('local_runtime_unsupported')
    device={k:info[k] for k in ('platform','total_bytes','cores')}
    key=hashlib.sha256((self_check.fingerprint(ROOT)+json.dumps(device,sort_keys=True)).encode()).hexdigest()
    path=base/'Settings/performance-self-check.json'
    previous=ch.get_json(path) if path.exists() else None
    reused=self_check.cache_valid(previous,key)
    if not reused:
        progress('self_testing',0,0)
        identifier=uuid.uuid4().hex
        if sys.platform=='win32':
            reply=runtime.rpc('offline',{'action':'self_test','id':identifier})
        else:
            task=base/'Vault/SelfTests'/identifier;task.mkdir(parents=True,mode=0o700)
            ch.put_json(task/'request.json',{'action':'self_test','runtime':runtime},True)
            reply=run_mac_worker(task,True)
        previous={k:reply[k] for k in ('checks','elapsed_seconds','profile','peak_rss_bytes','local_model_calls','slow')}
        previous.update(phase='ready',fingerprint=key,device=device,checked_at=time.time(),cloud_data_sent=False)
        if not self_check.cache_valid(previous,key):raise ValueError('self_test_failed')
        ch.put_json(path,previous)
    import assistant
    public={k:previous[k] for k in ('profile','elapsed_seconds','peak_rss_bytes','local_model_calls','slow')}
    public.update(phase='ready',data_processing='local_offline',version=assistant.VERSION,self_test_passed=True,self_test_reused=reused,
                  message='虚构表格和文档自检通过，已自动启用省内存模式。'+('本机处理较慢，任务会自动排队。' if previous['slow'] else ''))
    ch.put_json(base/'Settings/background-setup.json',public)
    return runtime


def setup(base):
    path=base/'Settings/background-setup.json'
    try:
        ch.put_json(path,{'phase':'waiting_for_slot','message':'正在后台检查本机运行环境。'})
        def progress(stage,n,total):ch.put_json(path,{'phase':stage,'downloaded':n,'total':total,'message':'正在用虚构材料检查表格、文档和断网保护。' if stage=='self_testing' else '正在后台准备本地组件。'})
        with runtime_lock(base):ensure_ready(base,progress)
    except Exception as error:ch.put_json(path,blocked(error))
    return ch.get_json(path)


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
        state(base,identifier,{'phase':'waiting_for_slot','message':'任务已排队，后台一次处理一个文件。'})
        def progress(stage,n,total):state(base,identifier,{'phase':stage,'downloaded':n,'total':total})
        with runtime_lock(base):
            runtime=ensure_ready(base,progress)
            state(base,identifier,{'phase':'processing_offline'})
            if sys.platform=='win32':
                from background_windows import execute
                reply=execute(base,task,request,progress,backend=runtime)
            else:
                performance.require_capacity(performance.hardware())
                ch.put_json(task/'request.json',dict(request,runtime=runtime))
                reply=run_mac_worker(task)
        public={k:reply[k] for k in ('kind','rows','input_rows','zero_match','paragraphs','entities','local_model_calls') if k in reply}
        name='result.xlsx' if reply['kind']=='table' else 'result.docx'
        state(base,identifier,{'phase':'completed','output':str(task/name),'cloud_data_sent':False,**public})
    except Exception as error:
        state(base,identifier,blocked(error))


def main():
    try:
        import assistant
        parser=argparse.ArgumentParser();parser.add_argument('action',choices=['setup','submit','status','run']);parser.add_argument('--input');parser.add_argument('--task');parser.add_argument('--id');parser.add_argument('--base');args=parser.parse_args()
        assistant.check_package();os.umask(0o077);base=assistant.initialise(Path(args.base) if args.base else None)
        if args.action=='setup':reply=setup(base)
        elif args.action=='submit':reply=submit(base,Path(args.input) if args.input else pick_file(),args.task)
        elif args.action=='status':reply=state(base,args.id)
        else:run(base,args.id);return 0
        print(json.dumps(reply,ensure_ascii=False));return 2 if reply.get('phase')=='blocked' else 0
    except Exception as error:
        print(json.dumps(blocked(error),ensure_ascii=False));return 2

if __name__=='__main__':sys.exit(main())
