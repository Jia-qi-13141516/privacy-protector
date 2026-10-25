"""Fixed offline worker; no UI, cloud API, arbitrary commands or external result channel."""
import hashlib,json,os,socket,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import task_channel as ch


def require_offline():
    if sys.platform=='darwin':
        for address in [('127.0.0.1',9),('1.1.1.1',443)]:
            s=socket.socket();s.settimeout(1)
            try:s.connect(address)
            except PermissionError:pass
            except OSError:raise ValueError('isolation_failed') from None
            else:raise ValueError('isolation_failed')
            finally:s.close()
    elif sys.platform=='linux':
        marker=Path('/etc/privacy-assistant-offline')
        if not marker.is_file() or marker.is_symlink() or marker.stat().st_uid!=0 or marker.stat().st_mode&0o022 or marker.read_text().strip()!='privacy-assistant-offline-v1':raise ValueError('isolation_failed')
        if {p.name for p in Path('/sys/class/net').iterdir()}!={'lo'} or len(Path('/proc/net/route').read_text().splitlines())>1:raise ValueError('isolation_failed')
    else:raise ValueError('isolation_failed')


def install_execution_guard(binary):
    def audit(event,args):
        if event.startswith('socket.') or event in ('os.system','os.exec','os.posix_spawn'):raise ValueError('isolation_failed')
        if event=='subprocess.Popen' and str(args[0])!=binary:raise ValueError('isolation_failed')
    sys.addaudithook(audit)


def execute(task,source,instruction,config):
    require_offline()
    import local_runtime,background_engine as engine
    if sys.platform=='linux':
        import performance
        performance.require_capacity(performance.hardware(),guest=True)
    if not isinstance(instruction,str) or not 1<=len(instruction)<=2000:raise ValueError('task_invalid')
    model=local_runtime.LocalModel(config,task)
    install_execution_guard(str(model.binary))
    suffix=source.suffix.lower()
    if suffix not in ('.xlsx','.csv','.txt','.md','.docx','.pdf'):raise ValueError('document_format')
    raw=ch.read(source,20*1024*1024 if suffix in ('.xlsx','.csv') else 5*1024*1024)
    snapshot=task/('original'+suffix);ch.write(snapshot,raw,True)
    digest=hashlib.sha256(raw).hexdigest();del raw
    result=(engine.table_job if suffix in ('.xlsx','.csv') else engine.document_job)(snapshot,task,instruction,model)
    result['performance']={'profile':'compact','model_calls':model.metrics,
                           'peak_rss_bytes':max([m['peak_rss_bytes'] for m in model.metrics] or [0])}
    if hashlib.sha256(ch.read(snapshot)).hexdigest()!=digest:raise ValueError('source_changed')
    ch.put_json(task/'receipt.json',{'input_sha256':digest,'network':'os_blocked','cloud_data_sent':False,
                'model':'Qwen2.5-1.5B-Instruct-Q4_K_M','human_confirmation':False,**result},True)
    return result


def main():
    try:
        require_offline() # Before reading the private request or any source file.
        task=Path(sys.argv[1]);request=ch.get_json(task/'request.json')
        if request.get('action')=='self_test':
            from self_check import run_offline
            result=run_offline(task,request['runtime'])
        else:result=execute(task,Path(request['source']),request['instruction'],request['runtime'])
        print(json.dumps({'phase':'completed',**result}));return 0
    except Exception as e:
        from background import safe_error
        print(json.dumps({'phase':'blocked','code':safe_error(e)}));return 2

if __name__=='__main__':sys.exit(main())
