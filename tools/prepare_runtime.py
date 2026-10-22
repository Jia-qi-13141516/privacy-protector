"""Build the bundled Windows runtime from pinned upstream archives."""
import hashlib,json,os,shutil,stat,tempfile,time,urllib.parse,urllib.request,zipfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parents[1]
HOSTS={'api.nuget.org','files.pythonhosted.org'}

def allowed(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):raise ValueError('unapproved_source')
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,allowed(newurl))
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()
def download(asset,cache):
    url=allowed(asset['url']);name=asset['file']
    if Path(name).name!=name:raise ValueError('invalid_file_name')
    path=cache/name
    if path.exists():
        if digest(path)!=asset['sha256']:raise ValueError('cache_integrity_failed')
        return path
    opener=urllib.request.build_opener(Redirect())
    for attempt in range(3):
        part=cache/(name+'.part')
        try:
            with opener.open(url,timeout=45) as response,part.open('wb') as out:
                allowed(response.geturl());total=0
                while True:
                    block=response.read(1048576)
                    if not block:break
                    total+=len(block)
                    if total>asset['max_bytes']:raise ValueError('archive_too_large')
                    out.write(block)
            if digest(part)!=asset['sha256']:raise ValueError('download_integrity_failed')
            part.replace(path);return path
        except OSError:
            if attempt==2:raise
            time.sleep(1)
        finally:part.unlink(missing_ok=True)
def extract(path,destination,prefix=''):
    with zipfile.ZipFile(path) as archive:
        if sum(x.file_size for x in archive.infolist())>250*1024**2:raise ValueError('expanded_limit')
        for item in archive.infolist():
            if not item.filename.startswith(prefix) or item.is_dir():continue
            name=item.filename[len(prefix):];parts=PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name or stat.S_ISLNK(item.external_attr>>16):raise ValueError('archive_path_rejected')
            target=destination.joinpath(*parts.parts);target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
def main():
    lock=json.loads((BASE/'tools/runtime-lock.json').read_text());cache=BASE/'.build-cache';cache.mkdir(exist_ok=True)
    runtime=BASE/'privacy-assistant/runtime';stage=Path(tempfile.mkdtemp(prefix='runtime-',dir=cache))
    try:
        for name,asset in lock['assets'].items():
            path=download(asset,cache)
            extract(path,stage if name=='python' else stage/'Lib/site-packages','tools/' if name=='python' else '')
        if not (stage/'python.exe').is_file() or not (stage/'LICENSE.txt').is_file():raise ValueError('incomplete_runtime')
        if runtime.exists():
            backup=cache/'previous-runtime'
            if backup.exists():shutil.rmtree(backup)
            runtime.rename(backup)
        stage.rename(runtime)
        print('Pinned Windows runtime prepared.')
    finally:
        if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':main()
