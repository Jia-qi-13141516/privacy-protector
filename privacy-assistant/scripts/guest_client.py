"""Agent-facing actions inside the persistent VM. Never names a host file."""
import argparse,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from task_channel import task_id,put_json,get_json,read,regular

def main():
    try:
        p=argparse.ArgumentParser();p.add_argument('action',choices=['new','status','submit']);p.add_argument('--id');p.add_argument('--kind',choices=['table','document'],default='table');a=p.parse_args()
        config=Path('/etc/privacy-assistant-guest.json');regular(config)
        if config.stat().st_uid!=0 or config.stat().st_mode&0o022:raise ValueError('unmanaged_guest')
        root=Path(json.loads(config.read_text())['queue']);regular(root)
        if a.action=='new':
            identifier=uuid.uuid4().hex
            put_json(root/('request-'+identifier+'.json'),{'version':1,'id':identifier,'action':'new_document' if a.kind=='document' else 'new_table'},exclusive=True)
            print(json.dumps({'id':identifier,'phase':'waiting_for_file'}));return 0
        identifier=task_id(a.id);folder=root/identifier
        if a.action=='submit':
            if get_json(folder/'status.json')['phase']!='ready_for_agent':raise ValueError('wrong_phase')
            read(folder/('result.txt' if get_json(folder/'status.json').get('kind')=='document' else 'result.csv')) # Size, symlink and hardlink checks; no CSV content printed.
            put_json(root/('request-'+identifier+'.json'),{'version':1,'id':identifier,'action':'submit_result'},exclusive=True)
            print(json.dumps({'id':identifier,'phase':'waiting_for_confirmation'}));return 0
        reply=get_json(folder/'status.json')
        if reply.get('phase')=='ready_for_agent':reply['workspace']=str(folder)
        print(json.dumps(reply));return 0
    except Exception:print('{"phase":"blocked","code":"local_bridge_not_ready"}');return 2
if __name__=='__main__':sys.exit(main())
