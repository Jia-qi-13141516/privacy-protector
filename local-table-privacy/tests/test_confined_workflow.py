"""No model call: test the full filesystem boundary + business transformation."""
import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import openpyxl
from test_privacy import fixture,RUN,ROOT

@unittest.skipUnless(sys.platform=='darwin','macOS end-to-end boundary')
class ConfinedWorkflow(unittest.TestCase):
    def test_protected_source_to_exchange_to_local_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);v=d/'vault';e=d/'exchange';v.mkdir();e.mkdir();raw,pol,_=fixture(v)
            common=[sys.executable,'-B',str(RUN),'--input',str(raw),'--policy',str(pol)]
            r=subprocess.run(common+['--out',str(v/'job')],capture_output=True,text=True);self.assertEqual(r.returncode,0)
            # Simulated human release, permitted here only because all data is fake.
            approved=e/'approved.csv';approved.write_bytes((v/'job/private/wave_0.csv').read_bytes())
            code='''import csv,sys,pathlib
try:pathlib.Path(sys.argv[1]).read_bytes()
except PermissionError:pass
else:sys.exit(9)
with open('approved.csv') as f:r=csv.DictReader(f);headers=r.fieldnames;rows=list(r)
rows=[r for r in rows if int(r['score'])>=30]
for r in rows:r['follow_up']='yes'
rows.reverse()
with open('result.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=headers+['follow_up']);w.writeheader();w.writerows(rows)
print('RESULT_READY_RAW_ACCESS_DENIED')
'''
            r=subprocess.run([sys.executable,str(ROOT/'scripts/agent_boundary.py'),'--vault',str(v),'--exchange',str(e),'--',sys.executable,'-I','-c',code,str(raw)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'RESULT_READY_RAW_ACCESS_DENIED')
            # Independent local approval matches the known source rule, not AI output.
            with (v/'job/private/wave_0.csv').open() as f:tokens=[r['person'] for r in csv.DictReader(f) if int(r['score'])>=30]
            q={'table':'wave_0','editable':[], 'derived':[{'output':'follow_up','kind':'category','mapping':{'需跟进':'yes','无需跟进':'no'}}],
              'selection':{'mode':'subset','tokens':tokens},'fields':[{'source':'original','column':0,'header':'学号'}, {'source':'result','column':'follow_up','header':'是否跟进'}]}
            (v/'import.json').write_text(json.dumps(q))
            r=subprocess.run(common+['--mode','prepare-import','--job',str(v/'job'),'--results',str(e/'result.csv'),'--import-policy',str(v/'import.json'),'--out',str(v/'restored')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout)
            w=openpyxl.load_workbook(v/'restored/private/ready-to-import.xlsx');rows=list(w.active.values)[1:];w.close()
            self.assertEqual(rows,[(f'{i:06d}','需跟进') for i in range(60) if 20+i%17>=30])
            self.assertEqual(sorted(x.name for x in e.iterdir()),['approved.csv','result.csv'])

if __name__=='__main__':unittest.main()
