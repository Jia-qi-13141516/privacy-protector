"""Verify current guest isolation, not merely the presence of a config file."""
import json,os,pwd,grp,subprocess,sys,re
from pathlib import Path

def rules():
    value=json.loads(subprocess.check_output(['/usr/sbin/nft','-j','list','ruleset'],timeout=10))
    def strip(v):
        if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k not in ('handle','metainfo')}
        if isinstance(v,list):return [strip(x) for x in v if not isinstance(x,dict) or 'metainfo' not in x]
        return v
    return strip(value)

def check(role):
    if role=='offline':
        sys.path.insert(0,'/opt/skill/scripts')
        import deidentify
        deidentify.isolation_check();return
    teacher=pwd.getpwnam('teacher')
    if teacher.pw_uid==0:raise ValueError('privileged_agent')
    for group in ('sudo','adm','disk','vboxsf'):
        try:
            g=grp.getgrnam(group)
            if 'teacher' in g.gr_mem or g.gr_gid==teacher.pw_gid:raise ValueError('privileged_agent')
        except KeyError:pass
    expected=Path('/var/lib/privacy-install/firewall.json')
    if expected.stat().st_uid!=0 or expected.stat().st_mode&0o022:raise ValueError('boundary_changed')
    if json.loads(expected.read_text())!=rules():raise ValueError('boundary_changed')
    for line in Path('/proc/mounts').read_text().splitlines():
        if line.split()[2] in ('vboxsf','9p','virtiofs','cifs','nfs','nfs4'):raise ValueError('shared_mount')

def desktop():
    prefix=['/usr/sbin/runuser','-u','teacher','--','/usr/bin/env','DISPLAY=:0','XAUTHORITY=/home/teacher/.Xauthority','/usr/bin/xwininfo']
    tree=subprocess.check_output(prefix+['-root','-tree'],timeout=10,stderr=subprocess.DEVNULL).decode()
    matches=re.findall(r'(0x[0-9a-f]+) "WorkBuddy":.*? ([0-9]+)x([0-9]+)',tree)
    for identifier,width,height in matches:
        if int(width)<200 or int(height)<200:continue
        info=subprocess.check_output(prefix+['-id',identifier],timeout=10,stderr=subprocess.DEVNULL).decode()
        if 'Map State: IsViewable' in info:return
    raise ValueError('desktop_not_ready')

if __name__=='__main__':
    # Called only from root-owned provisioning, before any business files exist.
    if os.geteuid()!=0:raise SystemExit(2)
    Path('/var/lib/privacy-install/firewall.json').write_text(json.dumps(rules(),sort_keys=True))
