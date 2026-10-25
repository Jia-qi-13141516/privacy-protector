"""Real OS users + real model. All fixtures below are invented, never user materials."""
import hashlib,json,os,pwd,signal,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path('/opt/privacy-protector');sys.path[:0]=[str(ROOT/'protector'),str(ROOT/'scripts'),str(ROOT/'skill/scripts'),str(ROOT/'runtime/Lib/site-packages')]
import protocol,unix_rpc,document_engine as doc
import openpyxl
USER=pwd.getpwnam('pp-agent');UID,GID=USER.pw_uid,USER.pw_gid
FILES=Path('/home/pp-agent/materials');FILES.mkdir(exist_ok=True);os.chown(FILES,UID,GID)
EXPORT=Path('/home/pp-agent/results');EXPORT.mkdir(exist_ok=True);os.chown(EXPORT,UID,GID)
SOCKET=Path('/run/privacy-protector-test')
ROWS=[['编号','姓名','待补材料数','已处理份数'],['S001','虚构任一',2,8],['S002','虚构任二',7,1],['S003','虚构任三',3,4],['S004','虚构任四',None,7],['S005','虚构任五',4,2],['S006','虚构任六',0,5]]
PARAS=['任清负责协调社区阅读活动，周荻负责物料。','任清尚未交出报名核对表，需要在下周一之前交给周荻。','许棠仍需确认周三下午的教室，再将场地结果告知任清。','周荻已经完成物料清单，该事项已结束，无需再次跟进。','林澈负责海报，海报已发布归档，不再安排相关工作。','任清收到许棠的确认后，还需要通知周荻准备物料。']
def fixture(name,data):
 p=FILES/name;p.write_bytes(data);p.chmod(0o600);os.chown(p,UID,GID);return p
RUN=uuid.uuid4().hex
book=openpyxl.Workbook()
for row in ROWS:book.active.append(row)
import io
buf=io.BytesIO();book.save(buf);book.close();table=fixture(RUN+'-虚构台账.xlsx',buf.getvalue());document=fixture(RUN+'-虚构纪要.docx',doc.make_docx('\n\n'.join(PARAS)))
def agent(payload):
 p=subprocess.run(['/usr/sbin/runuser','-u','pp-agent','--','/usr/bin/python3','-I',str(ROOT/'tests/agent_attack.py')],input=json.dumps(payload),capture_output=True,text=True,check=True)
 return json.loads(p.stdout)
def public(obj):return agent({'public_requests':[obj]})['public:0']
def private(obj):return unix_rpc.request(SOCKET/'private.sock',obj,private=True)
def wait(identifier):
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  r=public({'action':'status','id':identifier})
  if r.get('phase')=='blocked':raise AssertionError(r)
  if r.get('phase')=='waiting_for_confirmation':return r
  time.sleep(.3)
 raise TimeoutError('task did not complete')
deadline=time.monotonic()+300
while time.monotonic()<deadline:
 health=public({'action':'health'})
 if health.get('phase')=='blocked':raise AssertionError(health)
 if health.get('ready'):break
 time.sleep(.5)
else:raise TimeoutError('first-run self-test did not pass')
assert health['self_test_passed'] and health['boundary']=='separate_os_identity'
receipts=[];jobs=[]
for source,task,kind in [(table,'筛选待补材料数不低于3，按待补材料数从大到小排列，新增是否跟进为需跟进、优先级统一为2，统计记录数。','table'),(document,'整理未完成待办，保留负责人、交接对象和期限，排除已完成事项。','document')]:
 before=hashlib.sha256(source.read_bytes()).hexdigest()
 submitted=public({'action':'submit','task':task});identifier=submitted['id'];assert submitted['phase']=='waiting_for_file'
 selected=private({'action':'select','id':identifier,'path':str(source)});assert selected['phase']=='queued',selected
 assert selected['original_access']=='os_denied'
 p=Path('/var/lib/privacy-protector-test/jobs')/identifier
 attacks=agent({'id':identifier,'files':{'original':str(source),'snapshot':str(p/('original'+source.suffix)),'journal':str(p/'source-journal.json')},'try_private':True,
   'public_requests':[{'action':'select','id':identifier,'path':str(source)},{'action':'restore','id':identifier},{'action':'confirm','id':identifier,'destination':str(EXPORT/'stolen.xlsx')},{'action':'read','id':identifier},{'action':'submit','task':'统计记录数','uid':0}]})
 assert all(v for k,v in attacks.items() if ':' in k and not k.startswith('public:')) and attacks['private_denied'],attacks
 assert all('error' in v for k,v in attacks.items() if k.startswith('public:')),attacks
 state=wait(identifier);assert set(state)=={'id','phase','original_access'}
 assert hashlib.sha256(source.read_bytes()).hexdigest()==before
 response=private({'action':'review','id':identifier});assert response['phase']=='waiting_for_confirmation' and response['preview']
 result=p/('result.xlsx' if kind=='table' else 'result.docx')
 assert all(agent({'files':{'result':str(result)}}).values())
 if kind=='table':
  b=openpyxl.load_workbook(result);values=[list(x) for x in b['处理结果'].values];stats=dict(list(b['统计'].values)[1:]);b.close()
  expected=[ROWS[0]+['是否跟进','优先级']]+[r+['需跟进',2] for r in sorted([r for r in ROWS[1:] if r[2] is not None and r[2]>=3],key=lambda r:r[2],reverse=True)]
  assert values==expected and stats['待补材料数：合计']==14
 else:
  extracted=doc.docx_text(result.read_bytes());expected='待办事项摘录\n\n'+'\n\n'.join(str(i)+'. '+PARAS[j-1] for i,j in enumerate([2,3,6],1));assert extracted==expected,(extracted,expected)
 existing=EXPORT/('existing-'+identifier+result.suffix);existing.write_bytes(b'keep-existing');os.chown(existing,UID,GID)
 assert 'error' in private({'action':'confirm','id':identifier,'destination':str(existing)})
 assert existing.read_bytes()==b'keep-existing' and public({'action':'status','id':identifier})['phase']=='waiting_for_confirmation'
 dest=EXPORT/('confirmed-'+identifier+result.suffix)
 assert private({'action':'confirm','id':identifier,'destination':str(dest)})['phase']=='confirmed'
 assert hashlib.sha256(dest.read_bytes()).hexdigest()==hashlib.sha256(result.read_bytes()).hexdigest()
 assert dest.stat().st_uid==UID
 assert all(agent({'files':{'original_after_export':str(source)}}).values())
 jobs.append((identifier,source,before))
 worker=json.loads((p/'worker-receipt.json').read_text());assert worker['worker_uid']==2002
 if kind=='document':assert worker['local_model_calls']>=2 and len(worker['model_metrics'])>=2
 outcome={'matched_rows':len(values)-1,'quantity_sum':stats['待补材料数：合计'],'new_columns':['是否跟进','优先级']} if kind=='table' else {'paragraph_ids':[2,3,6],'exact_original_excerpt':True}
 receipts.append({'outcome':outcome,'worker_uid':worker['worker_uid'],'model_calls':worker['local_model_calls'],'model_metrics':worker['model_metrics'],'kind':kind,'original_read_denied':True,'permission_change_denied':True,'private_rpc_denied':True,'public_path_and_export_rejected':True,'original_unchanged':True,'result_exact':True,'confirmed_export_exact':True})
# Reuse the same protected original, without unlocking or re-copying it as the Agent.
old_id,protected,original_hash=jobs[0]
repeat=public({'action':'submit','task':'统计记录数'})['id']
r=private({'action':'select','id':repeat,'path':str(protected)});assert r['phase']=='queued',r
wait(repeat);assert all(agent({'files':{'reused_original':str(protected)}}).values())
assert private({'action':'cancel','id':repeat})['phase']=='cancelled'
# A user can rename/unlink an entry in their directory. Recover the exact protected
# snapshot only through a private, explicitly confirmed save action.
renamed=protected.with_name(RUN+'-renamed-original.xlsx');protected.rename(renamed)
r=private({'action':'restore','id':old_id});assert 'error' in r
recovered=EXPORT/('recovered-'+uuid.uuid4().hex+'.xlsx')
r=private({'action':'recover','id':old_id,'destination':str(recovered)});assert r.get('recovered')
assert hashlib.sha256(recovered.read_bytes()).hexdigest()==original_hash
assert all(agent({'files':{'renamed_original':str(renamed)}}).values())
# Linked sources are rejected, never followed into another file.
link=FILES/(RUN+'-link.csv');link.symlink_to(renamed)
id=public({'action':'submit','task':'统计记录数'})['id'];r=private({'action':'select','id':id,'path':str(link)});assert r['phase']=='blocked'
# Hard links and special files cannot be silently treated as protected inputs.
hard=fixture(RUN+'-hard.csv',b'id,n\nA,3\n');os.link(hard,FILES/(RUN+'-other-link.csv'))
fifo=FILES/(RUN+'-fifo.csv');os.mkfifo(fifo);os.chown(fifo,UID,GID)
for invalid in (hard,fifo):
 bad=public({'action':'submit','task':'统计记录数'})['id'];r=private({'action':'select','id':bad,'path':str(invalid)})
 assert r['phase']=='blocked' and r['original_access']=='not_verified'
 assert not any((Path('/var/lib/privacy-protector-test/jobs')/bad).glob('original.*'))
# Kernel identity wins over any request body. Even the worker cannot call the Agent API.
other=subprocess.run(['/usr/sbin/runuser','-u','pp-worker','--','/usr/bin/python3','-I',str(ROOT/'tests/agent_attack.py')],input=json.dumps({'public_requests':[{'action':'health'}]}),capture_output=True,text=True,check=True)
assert json.loads(other.stdout)['public:0']=={'error':'forbidden'}
# An Agent holding an already-open descriptor must prevent a protection claim.
busy=fixture(RUN+'-busy.csv',b'id,value\nA,3\n')
held=subprocess.Popen(['/usr/sbin/runuser','-u','pp-agent','--','/usr/bin/python3','-c','import sys,time;f=open(sys.argv[1],"rb");print("ready",flush=True);time.sleep(90)',str(busy)],stdout=subprocess.PIPE,text=True,start_new_session=True)
assert held.stdout.readline().strip()=='ready'
id=public({'action':'submit','task':'统计记录数'})['id'];r=private({'action':'select','id':id,'path':str(busy)})
assert r['phase']=='blocked' and r['code']=='source_busy' and r['original_access']!='os_denied',r
assert not (Path('/var/lib/privacy-protector-test/jobs')/id/'original.csv').exists()
os.killpg(held.pid,signal.SIGTERM);held.wait(timeout=10)
# No implicit unlocking on failure, but the trusted UI can explicitly restore.
r=private({'action':'restore','id':id});assert r['original_access']!='os_denied'
assert busy.stat().st_uid==UID
report={'scope':'disposable Linux VM, actual kernel identities; not Windows or macOS deployment acceptance',
        'readiness':health,'fictional_only':True,'same_processing_engines':True,'real_local_model_used':True,'flow':receipts,
        'protected_source_reused':True,'renamed_source_snapshot_recovered_exactly':True,'symlink_rejected':True,'hardlink_rejected':True,'fifo_rejected':True,'other_identity_denied':True,'existing_export_not_overwritten':True,'open_descriptor_detected_before_plaintext_read':True,'no_automatic_unseal':True,'explicit_private_recovery':True}
Path('/tmp/protector-e2e-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
