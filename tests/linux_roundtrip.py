import base64,csv,io,json,subprocess,uuid
from pathlib import Path
root=Path('/var/lib/privacy-control')
def rpc(request,offline=True):
 identifier=uuid.uuid4().hex;(root/(identifier+'.json')).write_text(json.dumps(request))
 cmd=['python3','-I','/opt/privacy-bridge/guest_rpc.py',identifier]
 if offline:cmd=['unshare','--net','--mount','--propagation','private','sh','-c','mount -t sysfs sysfs /sys; exec "$@"','sh']+cmd
 out=subprocess.run(cmd,capture_output=True,text=True)
 if out.returncode:raise RuntimeError(out.stderr)
 return json.loads(out.stdout)
identifier=uuid.uuid4().hex
rows=[['学号','姓名','分数']]+[[str(10000+i),'虚构学生'+str(i),i] for i in range(60)]
buf=io.StringIO();csv.writer(buf).writerows(rows)
request={'action':'input','id':identifier,'extension':'.csv','data':base64.b64encode(buf.getvalue().encode()).decode()}
assert rpc(request,False)=={'error':'isolation_failed'}
assert not (Path('/var/lib/privacy-tasks')/identifier).exists()
assert len(rpc(request)['schema']['fields'])==3
clean=rpc({'action':'prepare','id':identifier,'choices':['id','drop','number']})
content=base64.b64decode(clean['data']).decode();assert '虚构学生' not in content
reader=csv.DictReader(content.splitlines());headers=reader.fieldnames
selected=[dict(r,follow_up='yes',priority='2') for r in reader if int(r['measure_3'])>=40];selected.reverse()
buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=headers+['follow_up','priority']);w.writeheader();w.writerows(selected)
preview=rpc({'action':'preview','id':identifier,'data':base64.b64encode(buf.getvalue().encode()).decode()})['preview']
assert len(preview)==20
for r in preview:assert r['姓名']=='虚构学生'+str(int(r['学号'])-10000)
result=rpc({'action':'export','id':identifier})
import openpyxl
book=openpyxl.load_workbook(io.BytesIO(base64.b64decode(result['xlsx'])));actual=list(book.active.values);book.close()
assert actual[1:]==[(str(10000+i),'虚构学生'+str(i),str(i),'需跟进',2) for i in range(40,60)]
print(json.dumps({'networked_read_rejected':True,'offline_read_passed':True,'input_rows':60,'selected_rows':20,'identity_and_values_exact':True}))
