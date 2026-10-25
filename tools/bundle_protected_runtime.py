"""Prepare portable macOS runtimes and the trusted UI; never register a service."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parents[1];APP=BASE/'privacy-assistant'
sys.path.insert(0,str(APP/'scripts'))
from component_download import fetch

def extract(archive,dest):
    with tarfile.open(archive,'r:gz') as package:
        entries=package.getmembers()
        if len(entries)>15000 or sum(e.size for e in entries)>400*1024**2:raise ValueError('archive_limit')
        for entry in entries:
            p=PurePosixPath(entry.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='python':raise ValueError('archive_path')
            if entry.isdir():continue
            item=entry
            for _ in range(8):
                if not item.issym():break
                target=PurePosixPath(os.path.normpath(str(PurePosixPath(item.name).parent/item.linkname)))
                if target.is_absolute() or '..' in target.parts or target.parts[0]!='python':raise ValueError('archive_link')
                item=package.getmember(str(target))
            if not item.isfile():raise ValueError('archive_type')
            output=dest.joinpath(*p.parts[1:]);output.parent.mkdir(parents=True,exist_ok=True)
            output.write_bytes(package.extractfile(item).read());output.chmod(0o755 if item.mode&0o111 else 0o644)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['darwin-arm64','darwin-x86_64','all'],default='all');args=parser.parse_args()
    locks=json.loads((BASE/'tools/protector-runtime-lock.json').read_text());cache=BASE/'.build-cache';cache.mkdir(exist_ok=True)
    for key,asset in locks.items():
        if args.platform not in ('all',key):continue
        archive=fetch(asset,cache);dest=APP/('runtime-macos-'+key.split('-',1)[1])
        if dest.exists():shutil.rmtree(dest)
        dest.mkdir();extract(archive,dest)
    if sys.platform=='darwin':
        binaries=[]
        for arch in ('arm64','x86_64'):
            out=cache/('PrivacyProtectorUI-'+arch)
            subprocess.run(['/usr/bin/swiftc','-target',arch+'-apple-macosx13.3','-module-cache-path',str(cache/'swift'),'-O','-o',str(out),str(APP/'protector/macos_ui.swift')],check=True);binaries.append(str(out))
        subprocess.run(['/usr/bin/lipo','-create',*binaries,'-output',str(APP/'protector/PrivacyProtectorUI')],check=True)
    print('Protected runtime build inputs prepared; no installation performed.')
if __name__=='__main__':main()
