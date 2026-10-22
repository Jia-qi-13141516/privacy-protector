"""Root-owned guest endpoint. Only the host can place control requests.

There is no network listener and no generic shell or arbitrary-path method.
"""
import base64,json,os,sys
from pathlib import Path
sys.path.insert(0,'/opt/privacy-bridge')
from task_channel import task_id,read,write,get_json,put_json,guest_rpc,decode_blob,regular

CONTROL=Path('/var/lib/privacy-control')
TASKS=Path('/var/lib/privacy-tasks')
QUEUE=Path('/home/teacher/PrivacyTasks')

def offline(request):
    import table_wizard as wizard
    d=wizard.d;d.isolation_check()
    identifier=task_id(request.get('id'));task=TASKS/identifier
    action=request.get('action');private=task/'private'
    if action=='input' and set(request)=={'action','id','extension','data'}:
        if request['extension'] not in ('.csv','.xlsx'):raise ValueError('invalid_extension')
        if task.exists():raise ValueError('existing_task')
        private.mkdir(parents=True,mode=0o700)
        write(private/('original'+request['extension']),decode_blob(request['data']),True)
        wizard.inspect(task)
        return {'schema':get_json(private/'schema.json')}
    if action=='prepare' and set(request)=={'action','id','choices'}:
        put_json(private/'choices.json',request['choices']);wizard.configure(task)
        d.process(wizard.source_path(task),private/'policy.json',task/'job')
        return {'data':base64.b64encode(read(task/'job/private/students.csv')).decode(),'columns':wizard.column_guide(task)}
    if action=='preview' and set(request)=={'action','id','data'}:
        write(private/'returned.csv',decode_blob(request['data']));wizard.preview(task)
        return {'preview':get_json(private/'preview.json',20*1024*1024)}
    if action=='export' and set(request)=={'action','id'}:
        out=task/'export'
        if not out.exists():
            d.prepare_import(wizard.source_path(task),private/'policy.json',out,task/'job',private/'reviewed.csv',private/'import-policy.json')
        return {'xlsx':base64.b64encode(read(out/'private/ready-to-import.xlsx')).decode()}
    raise ValueError('invalid_request')

def online(request):
    if request.get('action')=='network' and set(request)=={'action','addresses'}:
        if not isinstance(request['addresses'],list) or len(request['addresses'])>64:raise ValueError('invalid_network')
        from network_policy import firewall
        import subprocess
        from guest_health import rules
        Path('/etc/nftables.conf').write_text(firewall(request['addresses']))
        subprocess.run(['/usr/sbin/nft','-f','/etc/nftables.conf'],check=True,capture_output=True,timeout=10)
        Path('/var/lib/privacy-install/firewall.json').write_text(json.dumps(rules(),sort_keys=True))
        return {'updated':True}
    # Queue files are untrusted. Drop root BEFORE any operation on them, so a
    # directory race cannot turn this transport into a privileged file reader.
    import pwd
    user=pwd.getpwnam('teacher')
    os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    return guest_rpc(QUEUE,request)

def main():
    try:
        identifier=task_id(sys.argv[1]);path=CONTROL/(identifier+'.json')
        if os.geteuid()!=0:raise ValueError('host_only')
        request=get_json(path,45*1024*1024);path.unlink()
        cfg=get_json(Path('/etc/privacy-assistant-guest.json'))
        if request=={'action':'desktop'} and cfg['role']=='online':
            from guest_health import desktop
            desktop();return {'visible':True}
        if request=={'action':'health'}:
            from guest_health import check
            check(cfg['role'])
            return {'status':'online' if cfg['role']=='online' else 'offline','version':1}
        return online(request) if cfg['role']=='online' else offline(request)
    except Exception as error:
        # Only a small fixed code set crosses the control channel.
        known={'isolation_failed','small_group','category_unknown','policy_invalid','active_content',
               'result_mismatch','duplicate_identity','unauthorized_change','numeric_invalid','job_mismatch'}
        return {'error':str(error) if str(error) in known else 'local_operation_failed'}

if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
