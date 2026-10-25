"""Disposable Linux guest only: restart must reuse self-test, preserve isolation."""
import hashlib,json,os,pwd,subprocess,sys,time
from pathlib import Path
assert sys.platform=='linux' and os.geteuid()==0
assert Path('/etc/privacy-protector-disposable-test').read_text().strip()=='fictional-materials-only'
root=Path('/opt/privacy-protector');sys.path[:0]=[str(root/'protector'),str(root/'scripts')]
import unix_rpc,protocol
store=Path('/var/lib/privacy-protector-test/jobs');receipt=store/'readiness.json'
before=receipt.read_bytes();subprocess.run(['systemctl','restart','privacy-protector-test'],check=True)
def public(obj):
    p=subprocess.run(['/usr/sbin/runuser','-u','pp-agent','--','/usr/bin/python3','-I',str(root/'tests/agent_attack.py')],input=json.dumps({'public_requests':[obj]}),capture_output=True,text=True,check=True)
    return json.loads(p.stdout)['public:0']
deadline=time.monotonic()+60
while time.monotonic()<deadline:
    try:health=public({'action':'health'})
    except Exception:time.sleep(.2);continue
    if health.get('phase')=='blocked':raise AssertionError(health)
    if health.get('ready'):break
    time.sleep(.2)
else:raise TimeoutError('service did not recover')
assert health['self_test_reused'] and health['self_test_passed']
assert receipt.read_bytes()==before
journals=[]
for p in store.glob('*/source-journal.json'):
    r=json.loads(p.read_text());source=Path(r['source'])
    if r['stage']=='verified' and source.exists():journals.append((p,r))
assert journals
for p,r in journals:
    probe=subprocess.run(['/usr/sbin/runuser','-u','pp-agent','--','/usr/bin/python3','-I',str(root/'tests/agent_attack.py')],input=json.dumps({'files':{'source':r['source'],'journal':str(p)}}),capture_output=True,text=True,check=True)
    assert all(json.loads(probe.stdout).values())
report={'scope':'disposable Linux service restart, not OS reboot or desktop-client acceptance','fictional_only':True,'cached_real_selftest_reused':True,'readiness_receipt_unchanged':True,'original_and_journal_still_denied':True,'self_test_receipt':json.loads(before)}
Path('/tmp/protector-restart-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
