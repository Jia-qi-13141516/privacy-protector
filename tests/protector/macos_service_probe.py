"""Disposable macOS CI only. Production installer/service, synthetic materials.

Private RPC simulates human selection/confirmation: this is not UI acceptance.
"""
import argparse,hashlib,io,json,os,platform,subprocess,sys,time,uuid
from pathlib import Path
assert sys.platform=='darwin' and os.geteuid()==0
assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True);p.add_argument('--report',required=True);args=p.parse_args()
source=Path(args.source).resolve();sys.path[:0]=[str(source/'protector'),str(source/'scripts'),str(source/'runtime/Lib/site-packages')]
import install_mac,install_common,unix_rpc,posix_store,document_engine as doc,openpyxl
manifest=hashlib.sha256((source/'release.json').read_bytes()).hexdigest()
plan=install_common.install_plan('darwin',args.uid,platform.machine())
assert not Path(plan['base']).exists(),'fresh hosted runner required'
result=install_mac.install(source,args.uid,args.gid,manifest,test=True)
assert result['service_registered'] and not result['ready']
app=Path(plan['app']);python=app/plan['python'];store=Path(plan['state'])/'Jobs';endpoint=Path(plan['socket_dir'])
# No credential files are copied or reset by this installer.
def public(obj):
    code='import sys,json;sys.path.insert(0,sys.argv[1]);import unix_rpc;print(json.dumps(unix_rpc.request(sys.argv[2],json.loads(sys.stdin.read()))))'
    r=subprocess.run([str(python),'-I','-B','-c',code,str(app/'protector'),str(endpoint/'public.sock')],input=json.dumps(obj),text=True,capture_output=True,user=args.uid,group=args.gid,extra_groups=[],timeout=15)
    if r.returncode:raise RuntimeError('public endpoint not ready')
    return json.loads(r.stdout)
def wait_ready():
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        try:h=public({'action':'health'})
        except Exception:time.sleep(2);continue
        if h.get('phase')=='blocked':raise AssertionError(h)
        if h.get('ready'):
            assert h['self_test_passed'];return h
        time.sleep(2)
    raise TimeoutError('protected first-run self-test did not finish')
ready=wait_ready();assert not ready['self_test_reused']
work=Path('/Users/Shared')/('PrivacyProtectorSynthetic-'+uuid.uuid4().hex);work.mkdir(mode=0o700);os.chown(work,args.uid,args.gid)
def fixture(name,blob):
    p=work/name;p.write_bytes(blob);p.chmod(0o600);os.chown(p,args.uid,args.gid);return p
def private(obj):return unix_rpc.request(endpoint/'private.sock',obj,private=True)
def wait_job(identifier):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        r=public({'action':'status','id':identifier})
        if r.get('phase')=='blocked':raise AssertionError(r)
        if r.get('phase')=='waiting_for_confirmation':return
        time.sleep(.3)
    raise TimeoutError('task not completed')
rows=[['编号','姓名','待补材料数'],['A001','虚构甲',2],['A002','虚构乙',7],['A003','虚构丙',3],['A004','虚构丁',4]]
b=openpyxl.Workbook()
for row in rows:b.active.append(row)
buf=io.BytesIO();b.save(buf);b.close();table=fixture('fictional.xlsx',buf.getvalue())
paras=['任清负责协调社区阅读活动，周荻负责物料。','任清尚未交出报名核对表，需要在下周一之前交给周荻。','许棠仍需确认周三下午的教室，再将场地结果告知任清。','周荻已经完成物料清单，该事项已结束，无需再次跟进。','林澈负责海报，海报已发布归档，不再安排相关工作。','任清收到许棠的确认后，还需要通知周荻准备物料。']
document=fixture('fictional.docx',doc.make_docx('\n\n'.join(paras)));checks=[]
for f,task,kind in [(table,'筛选待补材料数不低于3，按待补材料数从大到小排列，新增是否跟进为需跟进、优先级统一为2，统计记录数。','table'),(document,'整理未完成待办，保留负责人、交接对象和期限，排除已完成事项。','document')]:
    before=hashlib.sha256(f.read_bytes()).hexdigest();r=public({'action':'submit','task':task});identifier=r['id']
    assert r['phase']=='waiting_for_file'
    r=private({'action':'select','id':identifier,'path':str(f)});assert r['phase']=='queued',r
    assert posix_store.denied_as_user(f,args.uid,args.gid)
    wait_job(identifier);job=store/identifier;result=job/('result.xlsx' if kind=='table' else 'result.docx')
    assert posix_store.denied_as_user(result,args.uid,args.gid)
    assert 'error' in public({'action':'confirm','id':identifier,'destination':str(work/'unauthorized.xlsx')})
    assert private({'action':'review','id':identifier})['preview']
    if kind=='table':
        b=openpyxl.load_workbook(result);values=list(b['处理结果'].values);stats=dict(list(b['统计'].values)[1:]);b.close()
        expected=[tuple(rows[0]+['是否跟进','优先级'])]+[tuple(row+['需跟进',2]) for row in sorted(rows[2:],key=lambda row:row[2],reverse=True)]
        assert values==expected and stats['待补材料数：合计']==14
    else:
        expected='待办事项摘录\n\n'+'\n\n'.join(str(i)+'. '+paras[j-1] for i,j in enumerate([2,3,6],1))
        assert doc.docx_text(result.read_bytes())==expected
        receipt=json.loads((job/'worker-receipt.json').read_text());assert receipt['local_model_calls']>=2
    dest=work/('confirmed'+result.suffix)
    assert private({'action':'confirm','id':identifier,'destination':str(dest)})['phase']=='confirmed'
    assert dest.read_bytes()==result.read_bytes() and dest.stat().st_uid==args.uid
    assert hashlib.sha256(f.read_bytes()).hexdigest()==before and posix_store.denied_as_user(f,args.uid,args.gid)
    checks.append({'kind':kind,'exact_result':True,'ordinary_agent_original_and_result_denied':True,'confirmed_export_exact':True,'original_still_denied':True})
receipt_before=(store/'readiness.json').read_bytes()
# Same-version installation reuses the immutable copy and restarts the persistent service.
assert install_mac.install(source,args.uid,args.gid,manifest,test=True)['service_registered']
reused=wait_ready();assert reused['self_test_reused'];assert (store/'readiness.json').read_bytes()==receipt_before
for f in (table,document):assert posix_store.denied_as_user(f,args.uid,args.gid)
report={'scope':'disposable GitHub-hosted macOS; real privileged installer and service; simulated human private RPC, not UI/WorkBuddy acceptance','fictional_only':True,'architecture':platform.machine(),'system_version':platform.mac_ver()[0],'privileged_install_and_registration':True,'real_selftest_receipt':json.loads(receipt_before),'flow':checks,'repeat_install_and_service_restart':True,'cached_selftest_reused':True,'os_reboot_tested':False,'interactive_ui_tested':False,'workbuddy_tested':False,'physical_8gb_tested':False}
Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
subprocess.run(['/bin/launchctl','bootout','system/'+plan['service']],check=True)
