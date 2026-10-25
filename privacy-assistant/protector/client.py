"""Public Agent entry: task text in, status out. File selection is private UI only."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import protocol

def endpoint():
    if sys.platform in ('darwin','linux'):return Path('/private/var/run' if sys.platform=='darwin' else '/run')/('privacy-protector-'+str(os.getuid()))/'public.sock'
    if sys.platform=='win32':
        from windows_rpc import endpoint as windows_endpoint
        from windows_native import current_sid
        return windows_endpoint(current_sid())
    raise ValueError('unsupported_platform')

def request(obj,path=None):
    protocol.public_request(obj)
    if sys.platform=='win32':import windows_rpc as rpc
    elif sys.platform in ('darwin','linux'):import unix_rpc as rpc
    else:raise ValueError('unsupported_platform')
    return rpc.request(path or endpoint(),obj)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['submit','status','review','health']);p.add_argument('--task');p.add_argument('--id');a=p.parse_args()
    obj={'action':a.action}
    if a.action=='submit':obj['task']=a.task
    elif a.action in ('status','review'):obj['id']=a.id
    try:r=request(obj)
    except Exception as e:r=protocol.failure(e)
    print(json.dumps(r,ensure_ascii=False));return 2 if 'error' in r else 0
if __name__=='__main__':sys.exit(main())
