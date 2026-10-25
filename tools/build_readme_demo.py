"""0.10.0 demo: run the real offline workflow on fixed fictional inputs, then redraw it.

Nothing in the animation is a screen recording. Only verified, allowlisted fictional
values and bounded machine measurements enter the public report.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, shutil, subprocess, sys, time

ROWS=[['编号','姓名','待补材料数','已核对份数'],
 ['T001','虚构甲',2,4],['T002','虚构乙',3,2],['T003','虚构丙',0,1],['T004','虚构丁',5,1],
 ['T005','虚构戊',4,7],['T006','虚构己',1,0],['T007','虚构庚',3,6],['T008','虚构辛',6,3]]
PARAGRAPHS=[
 '顾衡是宋岚的项目联络人，宋岚负责社区读书活动的物料。',
 '顾衡尚未将报名核对表交给宋岚，需要在下周一之前完成交接。',
 '陶芷负责场地安排，仍需确认周三下午的教室，再把结果告知顾衡。',
 '宋岚已经核对完本周物料数量并把清单发给陶芷，该事项已结束，无需再次跟进。',
 '韩舟负责海报，海报已发布并归档，本周不再安排相关工作。',
 '顾衡收到陶芷的场地结果后，还需要通知宋岚准备物料。']
TABLE_TASK='筛选待补材料数不低于3，按待补材料数从大到小排列，新增是否跟进为需跟进、优先级统一为1，统计记录数。'
DOC_TASK='整理未完成待办，保留负责人、交接对象和期限，排除已结束事项与纯分工。'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def get(path):return json.loads(Path(path).read_text())
def wait_json(path,predicate,seconds=220):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if Path(path).exists():
   try:d=get(path)
   except (ValueError,OSError):d={}
   if d.get('phase')=='blocked':raise RuntimeError(d.get('code','blocked'))
   if predicate(d):return d
  time.sleep(.2)
 raise TimeoutError('Demo workflow did not finish')

def verify(args):
 package=Path(args.package_dir).resolve();work=Path(args.workdir).resolve();work.mkdir(parents=True,exist_ok=True)
 base=work/'fresh-install';assert not base.exists(),'Use a fresh workdir; never overwrite an existing installation.'
 sys.path.insert(0,str(package/'scripts'))
 import assistant,auto_setup,document_engine as doc,performance
 assert assistant.VERSION=='0.10.0';assistant.check_package()
 spec=get(package/'backend/local-model.json')
 if args.model_cache:
  source=Path(args.model_cache).resolve();assert sha(source)==spec['model']['sha256']
  (base/'Cache').mkdir(parents=True);shutil.copyfile(source,base/'Cache'/(spec['model']['sha256']+'.gguf'))
 setup=auto_setup.run('codex',base=base,skill_home=work/'test-skills')
 assert setup['status']=='background_installation_started'
 ready=wait_json(base/'Settings/background-setup.json',lambda x:x.get('phase')=='ready')
 assert ready['self_test_passed'] and not ready['self_test_reused']
 receipt=get(base/'Settings/performance-self-check.json');assert all(receipt['checks'].values())
 print('Fresh automatic self-check passed.',flush=True)
 import openpyxl
 inputs=work/'fictional-inputs';inputs.mkdir()
 book=openpyxl.Workbook();book.properties.creator='';book.properties.lastModifiedBy=''
 for row in ROWS:book.active.append(row)
 table=inputs/'fictional-table.xlsx';book.save(table);book.close()
 document=inputs/'fictional-minutes.docx';document.write_bytes(doc.make_docx('\n\n'.join(PARAGRAPHS)))
 before={p.name:sha(p) for p in (table,document)}
 entry=base/'App/0.10.0/scripts/background.py';jobs=[]
 for kind,path,task in [('table',table,TABLE_TASK),('document',document,DOC_TASK)]:
  result=subprocess.run([sys.executable,'-B',str(entry),'submit','--base',str(base),'--input',str(path),'--task',task],capture_output=True,text=True,check=True)
  job=json.loads(result.stdout);state=wait_json(base/'Settings/BackgroundJobs'/(job['id']+'.json'),lambda d:d.get('phase')=='completed')
  jobs.append((kind,base/'Vault/Background'/job['id'],state))
 assert all(sha(p)==before[p.name] for p in (table,document))
 table_dir=jobs[0][1];doc_dir=jobs[1][1]
 book=openpyxl.load_workbook(table_dir/'result.xlsx',data_only=False)
 values=[list(r) for r in book['处理结果'].values];stats=dict(list(book['统计'].values)[1:]);book.close()
 selected=sorted([r for r in ROWS[1:] if r[2]>=3],key=lambda r:r[2],reverse=True)
 expected=[ROWS[0]+['是否跟进','优先级']]+[r+['需跟进',1] for r in selected]
 assert values==expected and stats['符合条件记录数']==5 and stats['待补材料数：合计']==21
 ids=get(doc_dir/'source-index.json')['selected_ids'];assert ids==[2,3,6]
 output=doc.docx_text((doc_dir/'result.docx').read_bytes())
 expected_doc='待办事项摘录\n\n'+'\n\n'.join(str(i)+'. '+PARAGRAPHS[j-1] for i,j in enumerate(ids,1))
 assert output==expected_doc and jobs[1][2]['local_model_calls']==2
 assert jobs[0][2]['local_model_calls']==0
 # This is deliberately simulated hardware input, not an 8GB hardware test.
 try:performance.require_capacity({'platform':'darwin','total_bytes':8*1024**3,'available_bytes':1024**3,'cores':4})
 except ValueError as e:assert str(e)=='available_memory_low';low_ram='available_memory_low'
 else:raise AssertionError('Low-memory guard did not stop')
 report={
  'version':'0.10.0','date':datetime.date.today().isoformat(),'presentation':'redrawn_animation_not_screen_recording',
  'input_source':'fixed_fictional_literals_in_this_script','real_private_data_read':False,
  'hardware':{'chip':subprocess.check_output(['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'],text=True).strip(), 'ram_gib':round(receipt['device']['total_bytes']/1024**3,1),'platform':'macOS'},
  'first_self_check':{k:receipt[k] for k in ['checks','elapsed_seconds','peak_rss_bytes','local_model_calls','profile']},
  'installation':{'fresh_installation':True,'self_test_reused':False,'download_time_included':False,'existing_verified_model_cache_used':bool(args.model_cache)},
  'table':{'input_rows':ROWS,'output_rows':values,'selected_count':5,'selected_sum':21,'sorted_values':[r[2] for r in selected],'original_values_and_identities_match':True,'model_calls':0},
  'document':{'input_paragraphs':PARAGRAPHS,'selected_ids':ids,'output_paragraphs':[PARAGRAPHS[j-1] for j in ids],'exact_original_text':True,'local_model_calls':2},
  'originals_unchanged':True,'offline_worker_verified':True,
  'simulation':{'low_available_memory_guard':low_ram,'simulated_total_ram_gib':8,'simulated_available_ram_gib':1,'physical_hardware_test':False},
  'not_hardware_validated':['8GB computer','Windows / WorkBuddy','Intel Mac']}
 target=work/'demo-verification.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 # Do not publish logs, paths, runtime config, task IDs, model weights or private maps.
 print(json.dumps({'report':str(target),'self_check_seconds':receipt['elapsed_seconds'],'table_records':5,'document_paragraphs':len(ids),'local_model_calls':2,'originals_unchanged':True},ensure_ascii=False))

if __name__=='__main__':
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
 v=sub.add_parser('verify');v.add_argument('--package-dir',required=True);v.add_argument('--workdir',required=True);v.add_argument('--model-cache')
 args=parser.parse_args();verify(args)
