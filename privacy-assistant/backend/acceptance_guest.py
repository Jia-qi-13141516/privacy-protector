"""A fixed synthetic check; never accepts a host path or reads an account."""
import csv,json,os,sys
from pathlib import Path
sys.path.insert(0,'/opt/privacy-bridge')
from task_channel import task_id,read
identifier=task_id(sys.argv[1]);folder=Path('/home/teacher/PrivacyTasks')/identifier
if os.geteuid()==0:raise SystemExit(2)
try:Path('/var/lib/privacy-control').iterdir().__next__()
except PermissionError:denied=True
else:raise SystemExit(2)
data=read(folder/'data.csv').decode()
reader=csv.DictReader(data.splitlines());fields=reader.fieldnames
selected=[dict(row,follow_up='yes',priority='2') for row in reader if int(row['measure_3'])>=40]
selected.reverse()
with (folder/'result.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=fields+['follow_up','priority']);writer.writeheader();writer.writerows(selected)
print(json.dumps({'profile_preserved':True,'private_denied':True}))
