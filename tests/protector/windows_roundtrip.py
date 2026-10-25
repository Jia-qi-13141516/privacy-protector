"""Synthetic tasks through the production Windows service, on disposable CI only."""
import hashlib,io,json,os,sys,time,uuid
from pathlib import Path

def run(source,installed,sid,token):
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    sys.path[:0]=[str(source/'protector'),str(source/'scripts'),str(source/'runtime/Lib/site-packages')]
    import windows_native as win,windows_rpc as rpc,windows_store as permissions,document_engine as doc,openpyxl
    win.root_only();work=Path('C:/')/('PrivacyProtectorSynthetic-'+uuid.uuid4().hex);work.mkdir()
    acl=win.system_acl();acl.AddAccessAllowedAceEx(win.win32security.ACL_REVISION,3,win.rights.FILE_ALL_ACCESS,win.win32security.ConvertStringSidToSid(sid))
    win.win32security.SetNamedSecurityInfo(str(work),win.win32security.SE_FILE_OBJECT,win.win32security.DACL_SECURITY_INFORMATION|win.win32security.PROTECTED_DACL_SECURITY_INFORMATION,None,None,acl,None)
    def fixture(name,blob):
        p=work/name
        with win.impersonate(token):p.write_bytes(blob)
        return p
    def public(obj):
        with win.impersonate(token):return rpc.request(rpc.endpoint(sid),obj)
    def private(obj):return rpc.request(rpc.endpoint(sid,True),obj,private=True)
    def wait_job(identifier):
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            status=public({'action':'status','id':identifier})
            assert status.get('phase')!='blocked',status
            if status.get('phase')=='waiting_for_confirmation':return
            time.sleep(.5)
        raise TimeoutError('synthetic task did not complete')
    rows=[['编号','姓名','待补材料数'],['A001','虚构甲',2],['A002','虚构乙',7],['A003','虚构丙',3],['A004','虚构丁',4]]
    b=openpyxl.Workbook()
    for row in rows:b.active.append(row)
    buf=io.BytesIO();b.save(buf);b.close();table=fixture('fictional.xlsx',buf.getvalue())
    paras=['任清负责协调社区阅读活动，周荻负责物料。','任清尚未交出报名核对表，需要在下周一之前交给周荻。','许棠仍需确认周三下午的教室，再将场地结果告知任清。','周荻已经完成物料清单，该事项已结束，无需再次跟进。','林澈负责海报，海报已发布归档，不再安排相关工作。','任清收到许棠的确认后，还需要通知周荻准备物料。']
    document=fixture('fictional.docx',doc.make_docx('\n\n'.join(paras)));checks=[]
    for f,task,kind in [(table,'筛选待补材料数不低于3，按待补材料数从大到小排列，新增是否跟进为需跟进、优先级统一为2，统计记录数。','table'),(document,'整理未完成待办，保留负责人、交接对象和期限，排除已完成事项。','document')]:
        before=hashlib.sha256(f.read_bytes()).hexdigest();r=public({'action':'submit','task':task});identifier=r['id']
        assert r['phase']=='waiting_for_file',r
        r=private({'action':'select','id':identifier,'path':str(f)});assert r['phase']=='queued',r
        assert permissions.denied_as_user(f,sid)
        wait_job(identifier);job=installed/'State/Jobs'/identifier;result=job/('result.xlsx' if kind=='table' else 'result.docx')
        assert permissions.denied_as_user(result,sid)
        assert private({'action':'review','id':identifier})['preview']
        if kind=='table':
            b=openpyxl.load_workbook(result);values=list(b['处理结果'].values);stats=dict(list(b['统计'].values)[1:]);b.close()
            expected=[tuple(rows[0]+['是否跟进','优先级'])]+[tuple(row+['需跟进',2]) for row in sorted(rows[2:],key=lambda row:row[2],reverse=True)]
            assert values==expected and stats['待补材料数：合计']==14
        else:
            expected='待办事项摘录\n\n'+'\n\n'.join(str(i)+'. '+paras[j-1] for i,j in enumerate([2,3,6],1))
            assert doc.docx_text(result.read_bytes())==expected
            receipt=json.loads((job/'receipt.json').read_text(encoding='utf-8'));assert receipt['local_model_calls']>=2
        dest=work/('confirmed'+result.suffix)
        assert private({'action':'confirm','id':identifier,'destination':str(dest)})['phase']=='confirmed'
        with win.impersonate(token):exported=dest.read_bytes()
        assert exported==result.read_bytes()
        assert hashlib.sha256(f.read_bytes()).hexdigest()==before and permissions.denied_as_user(f,sid)
        checks.append({'kind':kind,'exact_result':True,'ordinary_agent_original_and_result_denied':True,'confirmed_export_exact':True,'original_still_denied':True})
    return checks
