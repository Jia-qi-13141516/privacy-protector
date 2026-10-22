"""Pinned HTTPS components, bounded disk use, atomic cache promotion."""
import hashlib,json,os,re,tempfile,time,urllib.parse,urllib.request
from pathlib import Path
from task_channel import regular

HOSTS={'download.virtualbox.org','cloud-images.ubuntu.com','download.codebuddy.cn','download.visualstudio.microsoft.com'}

def checked_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise ValueError('download_source_rejected')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,checked_url(newurl))

def digest(path):
    regular(path);h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def fetch(asset,cache,progress=lambda done,total:None):
    if set(asset)!={'url','sha256','max_bytes'} or not re.fullmatch('[a-f0-9]{64}',asset['sha256']):
        raise ValueError('component_lock_invalid')
    checked_url(asset['url']);limit=asset['max_bytes']
    if type(limit)!=int or not 1<=limit<=2*1024**3:raise ValueError('component_lock_invalid')
    regular(cache);cache.mkdir(parents=True,exist_ok=True)
    suffix=Path(urllib.parse.urlsplit(asset['url']).path).suffix
    dest=cache/(asset['sha256']+suffix);regular(dest)
    if dest.exists():
        if dest.stat().st_size<=limit and digest(dest)==asset['sha256']:return dest
        raise ValueError('cache_integrity_failed')
    opener=urllib.request.build_opener(Redirect())
    last_error=None
    for attempt in range(3):
        fd,name=tempfile.mkstemp(prefix='.download-',dir=cache)
        try:
            with os.fdopen(fd,'wb') as f,opener.open(urllib.request.Request(asset['url'],headers={'User-Agent':'PrivacyAssistant/0.6'}),timeout=45) as response:
                checked_url(response.geturl())
                if response.status!=200:raise ValueError('download_status_invalid')
                total=int(response.headers.get('Content-Length',0));done=0;h=hashlib.sha256();deadline=time.monotonic()+3600
                if total>limit:raise ValueError('download_too_large')
                while True:
                    if time.monotonic()>deadline:raise TimeoutError()
                    block=response.read(1024*1024)
                    if not block:break
                    done+=len(block)
                    if done>limit:raise ValueError('download_too_large')
                    f.write(block);h.update(block);progress(done,total)
                f.flush();os.fsync(f.fileno())
            if (total and done!=total) or h.hexdigest()!=asset['sha256']:raise ValueError('download_integrity_failed')
            regular(dest);os.replace(name,dest);return dest
        except ValueError:raise
        except (OSError,TimeoutError) as error:last_error=type(error).__name__
        finally:
            if os.path.exists(name):os.unlink(name)
    raise ValueError('component_download_failed') from None
