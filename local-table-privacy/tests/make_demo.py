#!/usr/bin/env python3
"""Create a retained, explicitly fictional local demonstration; never ingest user files."""
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import openpyxl
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_privacy import fixture, RUN


def main():
    if len(sys.argv)!=2:
        print('A new local demo directory is required.');return 2
    dest=Path(sys.argv[1])
    if dest.exists():
        print('Demo destination must not exist.');return 2
    dest.mkdir(parents=True,mode=0o700)
    raw,policy,_=fixture(dest)
    job=dest/'deidentified';imported=dest/'import-ready'
    common=[sys.executable,'-B',str(RUN),'--input',str(raw),'--policy',str(policy)]
    started=time.perf_counter()
    run=subprocess.run(common+['--out',str(job)],capture_output=True,text=True)
    if run.returncode:
        print('Synthetic preprocessing failed.');return 2
    deidentify_seconds=time.perf_counter()-started
    source=job/'private/wave_0.csv'
    with source.open() as f:reader=csv.DictReader(f);names=reader.fieldnames;rows=list(reader)
    # Deterministic synthetic stand-in for a permitted result transformation.
    for r in rows:r['score']=str(int(r['score'])+1)
    rows.reverse()
    result=dest/'results.csv'
    with result.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=names);w.writeheader();w.writerows(rows)
    spec={'table':'wave_0','editable':['score'],'fields':[
        {'source':'original','column':0,'header':'学号'},
        {'source':'original','column':1,'header':'姓名'},
        {'source':'result','column':'score','header':'更新分数'}]}
    ip=dest/'import-policy.json';ip.write_text(json.dumps(spec,ensure_ascii=False,indent=2))
    started=time.perf_counter()
    run=subprocess.run(common+['--mode','prepare-import','--job',str(job),'--results',str(result),
                               '--import-policy',str(ip),'--out',str(imported)],capture_output=True,text=True)
    if run.returncode:
        print('Synthetic identity restoration failed.');return 2
    restore_seconds=time.perf_counter()-started
    wb=openpyxl.load_workbook(imported/'private/ready-to-import.xlsx');import_rows=list(wb.active.values)[1:];wb.close()
    db=sqlite3.connect(dest/'synthetic-system.sqlite');db.execute('CREATE TABLE students(id TEXT PRIMARY KEY,name TEXT,score REAL)')
    db.executemany('INSERT INTO students VALUES(?,?,?)',import_rows);db.commit()
    actual=db.execute('SELECT id,name,score FROM students ORDER BY id').fetchall();db.close()
    expected=[(f'{i:06d}',f'虚构学生{i:03d}',21+i%17) for i in range(60)]
    assert actual==expected
    with (imported/'private/ready-to-paste.tsv').open(encoding='utf-8') as f:paste=list(csv.reader(f,delimiter='\t'))[1:]
    assert [(r[0],r[1],float(r[2])) for r in paste]==expected
    metrics=json.loads((job/'private/statistics.json').read_text())
    a=metrics['before'][0];b=metrics['after'][0]
    report={'fictional_data_only':True,'rows_per_wave':60,'waves':2,
            'network_denied':True,'model_received_raw_data':False,'model_called':False,
            'comparison':{'score_mean':[a['numeric']['score']['mean'],b['numeric']['score']['mean']],
                          'score_variance':[a['numeric']['score']['variance'],b['numeric']['score']['variance']],
                          'outcome_missing':[a['numeric']['outcome']['missing'],b['numeric']['outcome']['missing']],
                          'correlation':[a['correlations']['score__outcome']['r'],b['correlations']['score__outcome']['r']],
                          'paired_mean_change':[metrics['paired_before']['differences']['score']['mean'],metrics['paired_after']['differences']['score']['mean']]},
            'all_checked_values_equal':metrics['before']==metrics['after'] and metrics['paired_before']==metrics['paired_after'],
            'local_restoration':{'shuffled_result_rows':True,'allowed_score_change':1,'identity_and_value_matches':len(actual),
                                 'simulated_system_rows':60,'paste_matches':60,'real_system_submitted':False,'clipboard_written':False},
            'observed_seconds':{'deidentify':round(deidentify_seconds,3),'restore':round(restore_seconds,3)}}
    # New business path: derive bounded columns, authorize a subset locally,
    # and independently compare restored identities against the known fixture.
    with source.open() as f: selected=list(csv.DictReader(f))
    selected=[r for r in selected if int(r['score'])>=30]
    selected_tokens=[r['person'] for r in selected]
    for r in selected:r.update(follow_up='yes',priority='2')
    selected.reverse()
    subset_result=dest/'subset-results.csv'
    with subset_result.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=names+['follow_up','priority']);writer.writeheader();writer.writerows(selected)
    subset_spec={'table':'wave_0','editable':[],
        'derived':[{'kind':'category','output':'follow_up','mapping':{'需跟进':'yes','无需跟进':'no'}},
                   {'kind':'number','output':'priority','min':0,'max':3,'nullable':False}],
        'selection':{'mode':'subset','tokens':selected_tokens},
        'fields':[{'source':'original','column':0,'header':'学号'},{'source':'original','column':1,'header':'姓名'},
                  {'source':'result','column':'follow_up','header':'是否跟进'},{'source':'result','column':'priority','header':'优先级'}]}
    subset_policy=dest/'subset-import-policy.json';subset_policy.write_text(json.dumps(subset_spec,ensure_ascii=False,indent=2))
    subset_out=dest/'subset-import'
    r=subprocess.run(common+['--mode','prepare-import','--job',str(job),'--results',str(subset_result),
                             '--import-policy',str(subset_policy),'--out',str(subset_out)],capture_output=True,text=True)
    assert r.returncode==0
    w=openpyxl.load_workbook(subset_out/'private/ready-to-import.xlsx');actual_subset=list(w.active.values)[1:];w.close()
    expected_subset=[(f'{i:06d}',f'虚构学生{i:03d}','需跟进',2) for i in range(60) if 20+i%17>=30]
    assert actual_subset==expected_subset
    report['derived_subset']={'exact_identity_and_value_match':True,'rows':len(actual_subset),'new_columns':2,
                              'selection_approval_simulated_on_fictional_data':True,'real_model_quality_tested':False}
    (dest/'synthetic-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    # All retained files, including fake source rows, are local and owner-only.
    for path in dest.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__':
    sys.exit(main())
