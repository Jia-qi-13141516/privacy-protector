"""macOS CLI confinement. Does not retrofit a running GUI/Agent session."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tempfile


def profile(vault, protected=(), readonly=()):
    p=json.dumps(str(vault.resolve()),ensure_ascii=False)
    return '\n'.join(['(version 1)', '(allow default)',
        '(deny file-read* file-write* (subpath '+p+'))',
        '(deny mach-lookup)', '(deny appleevent-send)',
        '(deny network-inbound)',
        '(deny network-outbound (remote ip "localhost:*"))',
        '(deny network-outbound (remote unix-socket))',
        # Narrow OS DNS socket exception; never allow general local tool bridges.
        '(allow network-outbound (literal "/private/var/run/mDNSResponder"))'] +
        ['(deny file-read* file-write* (literal ' + json.dumps(str(Path(x).resolve()),ensure_ascii=False) + '))' for x in protected] +
        ['(deny file-write* (subpath ' + json.dumps(str(Path(x).resolve()),ensure_ascii=False) + '))' for x in readonly])


def paths(vault, exchange):
    from deidentify import safe_path
    safe_path(vault);safe_path(exchange)
    vault=vault.resolve(strict=True);exchange=exchange.resolve(strict=True)
    if not vault.is_dir() or not exchange.is_dir() or vault==exchange or vault in exchange.parents or exchange in vault.parents:
        raise ValueError('boundary_overlap')
    # Existing hard links outside the protected path would defeat a path boundary.
    # Inspect metadata only, never contents, before starting a new Agent process.
    for root in (vault,exchange):
        for item in root.rglob('*'):
            safe_path(item)
            if item.is_file() and item.stat().st_nlink!=1:raise ValueError('linked_file')
    return vault,exchange


def main():
    try:
        p=argparse.ArgumentParser();p.add_argument('--vault',required=True);p.add_argument('--exchange',required=True)
        p.add_argument('--check',action='store_true');p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
        if sys.platform!='darwin':raise ValueError('unsupported')
        vault,exchange=paths(Path(a.vault),Path(a.exchange))
        # Only a newly created synthetic canary is opened by this launcher.
        fd,canary=tempfile.mkstemp(prefix='.boundary-',dir=vault);os.write(fd,b'LOCAL_SYNTHETIC_CANARY');os.close(fd)
        env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG','LC_ALL','TERM') if k in os.environ}
        sb=['/usr/bin/sandbox-exec','-p',profile(vault)]
        probe="import pathlib,sys\np=pathlib.Path(sys.argv[1])\ntry: p.read_bytes()\nexcept PermissionError: pass\nelse: sys.exit(2)\ntry: p.write_bytes(b'changed')\nexcept PermissionError: pass\nelse: sys.exit(3)\nprint('BOUNDARY_OK')"
        try:
            r=subprocess.run(sb+[sys.executable,'-I','-B','-c',probe,canary],capture_output=True,text=True,env=env,timeout=15,close_fds=True)
        finally:Path(canary).unlink(missing_ok=True)
        if r.returncode or r.stdout.strip()!='BOUNDARY_OK':raise ValueError('boundary_failed')
        if a.check:
            print(json.dumps({'status':'boundary_probe_passed','scope':'new_cli_children_only','existing_agents_isolated':False}));return 0
        cmd=a.command[1:] if a.command[:1]==['--'] else a.command
        if not cmd:raise ValueError('command_required')
        # No open raw-file descriptor, inherited custom env, local IPC or GUI bridge.
        return subprocess.run(sb+cmd,cwd=exchange,env=env,close_fds=True).returncode
    except Exception:
        print(json.dumps({'status':'blocked','code':'boundary_not_active','cloud_release':False}));return 2

if __name__=='__main__':sys.exit(main())
