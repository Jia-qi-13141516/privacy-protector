"""Privileged macOS install/update. Never invoked automatically during development."""
import argparse,grp,hashlib,json,os,plistlib,pwd,shutil,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from install_common import copy_verified,install_plan,qualification

def cmd(args):return subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,text=True).stdout

def directory(path,mode=0o755,gid=0):
    p=Path(path)
    for item in reversed((p,*p.parents)):
        if item.exists():
            st=item.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('private_store_insecure')
        else:item.mkdir(mode=0o755)
    os.chown(p,0,gid);p.chmod(mode);return p

def account(uid):
    name='_pp'+str(uid)
    try:
        u=pwd.getpwnam(name)
        if u.pw_shell!='/usr/bin/false' or u.pw_dir!='/var/empty':raise ValueError('account_conflict')
        return u.pw_uid,u.pw_gid
    except KeyError:pass
    used={u.pw_uid for u in pwd.getpwall()}|{g.gr_gid for g in grp.getgrall()}
    number=next(x for x in range(60000,64000) if x not in used)
    for args in [('-create','/Groups/'+name),('-create','/Groups/'+name,'PrimaryGroupID',str(number)),
                 ('-create','/Users/'+name),('-create','/Users/'+name,'UniqueID',str(number)),
                 ('-create','/Users/'+name,'PrimaryGroupID',str(number)),('-create','/Users/'+name,'UserShell','/usr/bin/false'),
                 ('-create','/Users/'+name,'NFSHomeDirectory','/var/empty'),('-create','/Users/'+name,'IsHidden','1'),
                 ('-create','/Users/'+name,'Password','*')]:cmd(['/usr/bin/dscl','.',*args])
    return number,number

def install(source,uid,gid,expected,test=False):
    if sys.platform!='darwin' or os.geteuid()!=0 or uid<=0:raise ValueError('protection_unavailable')
    if pwd.getpwuid(uid).pw_gid!=gid:raise ValueError('invalid_request')
    qualification(source,test)
    import platform
    plan=install_plan('darwin',uid,platform.machine());base=directory(plan['base'])
    directory(base/'App');app=copy_verified(source,base/'App',expected)
    for p in [app,*app.rglob('*')]:
        os.chown(p,0,0);p.chmod(0o755 if p.is_dir() or p.stat().st_mode&0o111 or p.name=='PrivacyProtectorUI' else 0o644)
    executable=app/plan['python'];ui=app/'protector/PrivacyProtectorUI'
    if not executable.is_file() or not ui.is_file():raise ValueError('component_missing')
    worker_uid,worker_gid=account(uid)
    state=directory(plan['state'],0o700);store=directory(state/'Jobs',0o700)
    directory(base/'Workers');work=directory(plan['work'],0o750,worker_gid)
    directory(plan['socket_dir'])
    config=state/'config.json'
    existing=json.loads(config.read_text()) if config.exists() else {}
    if existing and (existing.get('uid')!=uid or existing.get('worker_uid')!=worker_uid):raise ValueError('account_conflict')
    value={'uid':uid,'gid':gid,'worker_uid':worker_uid,'worker_gid':worker_gid,'root':str(app),'store':str(store),'work':str(work),'socket_dir':plan['socket_dir'],'ui':str(ui),'runtime':existing.get('runtime')}
    # Stop only this product's enrolled service, retaining the private journal.
    cmdline=['/bin/launchctl','bootout','system/'+plan['service']]
    subprocess.run(cmdline,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    import posix_store
    posix_store.atomic_json(config,value)
    plist=Path('/Library/LaunchDaemons')/(plan['service']+'.plist')
    if plist.is_symlink():raise ValueError('private_store_insecure')
    contents={'Label':plan['service'],'ProgramArguments':[str(executable),'-I','-B',str(app/'protector/service.py'),'--config',str(config)],'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':60,'ProcessType':'Background','Umask':0o077,
              'StandardOutPath':str(state/'service.log'),'StandardErrorPath':str(state/'service.log')}
    temporary=plist.with_suffix('.new');temporary.write_bytes(plistlib.dumps(contents));temporary.chmod(0o644);os.chown(temporary,0,0);os.replace(temporary,plist)
    cmd(['/bin/launchctl','bootstrap','system',str(plist)])
    return {'phase':'preparing','service_registered':True,'ready':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True);p.add_argument('--manifest-sha',required=True);p.add_argument('--test-install',action='store_true');a=p.parse_args()
    try:r=install(Path(a.source),a.uid,a.gid,a.manifest_sha,a.test_install)
    except Exception:r={'phase':'blocked','code':'installation_failed','ready':False}
    print(json.dumps(r));sys.exit(0 if r['phase']!='blocked' else 2)
