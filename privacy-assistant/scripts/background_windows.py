"""Host-controlled offline VM execution. WorkBuddy never receives document or table contents."""
import base64,json,subprocess
from pathlib import Path
import task_channel as ch
import local_runtime
import performance
from vm_backend import Backend,preflight,install_engine
from component_download import digest

ROOT=Path(__file__).resolve().parents[1]


def prepare(base,progress):
    preflight(base)
    # Account for the VM's existing allocation instead of requiring it twice.
    existing=Backend(base)
    entry=existing.state['machines'].get('offline',{})
    running=bool(entry.get('ready') and existing.info('offline').get('VMState')=='running')
    performance.require_capacity(performance.hardware(),vm_running=running)
    config=local_runtime.install(base,'linux-x86_64',progress)
    backend=Backend(base,install_engine(base,progress));backend.provision(progress,roles=('offline',))
    info=backend.info('offline')
    if int(info.get('memory','0'))<3072:
        backend.shutdown('offline');backend.cli('modifyvm',backend.state['machines']['offline']['id'],'--memory','3072')
    backend.start('offline')
    from bridge_bundle import update
    update(backend,ROOT,roles=('offline',))
    spec=local_runtime.lock();entry=backend.state['machines']['offline']
    expected=spec['model']['sha256']+spec['runtimes']['linux-x86_64']['sha256']
    if entry.get('local_model_version')!=expected:
        backend.guest('offline','/usr/bin/mkdir',['-p','/opt/privacy-local/Cache'])
        for key in ('archive','model'):
            path=Path(config[key]);remote='/opt/privacy-local/Cache/'+path.name
            backend.cli('guestcontrol',entry['id'],'copyto',*backend.credentials('offline'),str(path),remote,timeout=900)
        code="import sys;sys.path.insert(0,'/opt/privacy-bridge');from pathlib import Path;from background_worker import require_offline;require_offline();import local_runtime,task_channel;config=local_runtime.install(Path('/opt/privacy-local'),'linux-x86_64');local_runtime.verify(config);task_channel.put_json(Path('/opt/privacy-local/config.json'),config);print('local_runtime_ready')"
        if backend.guest('offline','/usr/bin/python3',['-I','-c',code],timeout=600).strip()!='local_runtime_ready':raise ValueError('runtime_integrity')
        entry['local_model_version']=expected;backend.save()
    if backend.rpc('offline',{'action':'health'}).get('status')!='offline':raise ValueError('isolation_failed')
    backend.rpc('offline',{'action':'resource_health'})
    return backend


def execute(base,task,request,progress,backend=None):
    # Provisioning/downloads happen before loading any source bytes.
    backend=backend or prepare(base,progress);source=Path(request['source'])
    performance.require_capacity(performance.hardware(),vm_running=True)
    backend.rpc('offline',{'action':'resource_health'})
    from windows_service import safe_source
    raw=safe_source(source,document=source.suffix.lower() not in ('.csv','.xlsx'))
    progress('processing_offline',0,0)
    response=backend.rpc('offline',{'action':'background_task','id':task.name,'extension':source.suffix.lower(),
                       'data':base64.b64encode(raw).decode(),'instruction':request['instruction']})
    result=response['receipt']
    if result.get('result_name') not in ('result.xlsx','result.docx'):raise ValueError('export_integrity')
    ch.write(task/result['result_name'],ch.decode_blob(response['data']),True)
    ch.put_json(task/'receipt.json',dict(result,network='offline_vm_no_nic',cloud_data_sent=False,human_confirmation=False),True)
    return dict(result,phase='completed')
