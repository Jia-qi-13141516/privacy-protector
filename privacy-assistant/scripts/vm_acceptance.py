"""First-install synthetic end-to-end acceptance, then live boundary checks."""
import base64,csv,io,json,uuid,time
from task_channel import decode_blob

def verify(backend):
    for role in ('offline','online'):
        backend.start(role)
        if backend.rpc(role,{'action':'health'})['status']!=role:raise ValueError('health_failed')
    deadline=time.monotonic()+180
    while True:
        try:
            if backend.rpc('online',{'action':'desktop'}).get('visible') is not True:raise ValueError('desktop_not_ready')
            break
        except ValueError:
            if time.monotonic()>=deadline:raise ValueError('desktop_not_ready') from None
            time.sleep(2)
    if backend.state.get('acceptance_version')==1:return
    identifier=uuid.uuid4().hex
    rows=[['学号','姓名','分数']]+[[str(10000+i),'虚构学生'+str(i),i] for i in range(60)]
    stream=io.StringIO(newline='');csv.writer(stream).writerows(rows)
    schema=backend.rpc('offline',{'action':'input','id':identifier,'extension':'.csv','data':base64.b64encode(stream.getvalue().encode()).decode()})
    if len(schema['schema']['fields'])!=3:raise ValueError('acceptance_schema_failed')
    data=backend.rpc('offline',{'action':'prepare','id':identifier,'choices':['id','drop','number']})['data']
    decoded=decode_blob(data).decode()
    if '虚构学生' in decoded or '学号' in decoded:raise ValueError('acceptance_leak')
    backend.rpc('online',{'action':'deliver','id':identifier,'data':data})
    # Read as the actual unprivileged user after a full shutdown/start cycle.
    backend.shutdown('online');backend.start('online')
    result=backend.guest('online','/usr/sbin/runuser',['-u','teacher','--','/usr/bin/python3','-I','/opt/privacy-bridge/acceptance_guest.py',identifier])
    if json.loads(result)!={'profile_preserved':True,'private_denied':True}:raise ValueError('acceptance_boundary_failed')
    csv_result=backend.rpc('online',{'action':'result','id':identifier})['data']
    preview=backend.rpc('offline',{'action':'preview','id':identifier,'data':csv_result})['preview']
    expected=[{'学号':str(10000+i),'姓名':'虚构学生'+str(i),'分数':str(i),'是否跟进':'需跟进','优先级':'2'} for i in range(40,60)]
    # The model-side example intentionally reverses row order; verify identity keys.
    if sorted(preview,key=lambda r:r['学号'])!=expected:raise ValueError('acceptance_restore_failed')
    exported=decode_blob(backend.rpc('offline',{'action':'export','id':identifier})['xlsx'])
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(exported),read_only=True,data_only=False)
    actual=list(book.active.values);book.close()
    if actual[1:]!=[tuple([str(10000+i),'虚构学生'+str(i),str(i),'需跟进',2]) for i in range(40,60)]:raise ValueError('acceptance_export_failed')
    backend.state['acceptance_version']=1;backend.save()
