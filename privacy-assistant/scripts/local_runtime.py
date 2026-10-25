"""Pinned local inference. Downloads finish before any original is opened."""
import hashlib,json,os,platform,posixpath,shutil,subprocess,tarfile,tempfile
from pathlib import Path,PurePosixPath
import task_channel as ch
import performance
from component_download import fetch,digest

ROOT=Path(__file__).resolve().parents[1]


def lock():
    local=Path(__file__).parent/'local-model.json'
    return ch.get_json(local if local.exists() else ROOT/'backend/local-model.json')


def archive_files(archive):
    with tarfile.open(archive,'r:gz') as package:
        members=package.getmembers()
        if len(members)>1000 or sum(x.size for x in members)>300*1024*1024:raise ValueError('runtime_archive_invalid')
        for entry in members:
            name=PurePosixPath(entry.name)
            if name.is_absolute() or '..' in name.parts or '\\' in entry.name or ':' in entry.name:raise ValueError('runtime_archive_invalid')
            if entry.isdir():continue
            member=entry
            for _ in range(8):
                if not member.issym():break
                if '\\' in member.linkname or ':' in member.linkname:raise ValueError('runtime_archive_invalid')
                resolved=PurePosixPath(posixpath.normpath(str(PurePosixPath(member.name).parent/member.linkname)))
                if resolved.is_absolute() or '..' in resolved.parts:raise ValueError('runtime_archive_invalid')
                try:member=package.getmember(str(resolved))
                except KeyError:raise ValueError('runtime_archive_invalid') from None
            if not member.isfile():raise ValueError('runtime_archive_invalid')
            yield str(name),package.extractfile(member).read(),member.mode


def install(base,platform_key=None,progress=lambda *args:None):
    key=platform_key or ('darwin' if platform.system()=='Darwin' else 'linux')+'-'+platform.machine().lower()
    spec=lock();asset=spec['runtimes'].get(key)
    if asset is None:raise ValueError('local_runtime_unsupported')
    home=base/'LocalModel';ch.regular(home);home.mkdir(parents=True,exist_ok=True,mode=0o700)
    # No original-file arguments or contents are available to the downloader.
    bundled=ROOT/'runtime/inference-assets'/(asset['sha256']+'.gz')
    if bundled.exists():
        if digest(bundled)!=asset['sha256']:raise ValueError('runtime_integrity')
        archive=bundled
    else:archive=fetch(asset,base/'Cache',lambda n,t:progress('downloading_runtime',n,t))
    target=home/('runtime-'+asset['sha256'][:12]);ch.regular(target)
    if not target.exists():
        stage=Path(tempfile.mkdtemp(prefix='.runtime-',dir=home))
        try:
            manifest={}
            for name,data,mode in archive_files(archive):
                dest=stage/name;ch.write(dest,data,True);dest.chmod(0o700 if mode&0o111 else 0o600)
                manifest[name]=hashlib.sha256(data).hexdigest()
            binaries=[p for p in stage.rglob('llama-completion') if p.is_file()]
            if len(binaries)!=1:raise ValueError('runtime_archive_invalid')
            receipt={'files':manifest,'binary':str(binaries[0].relative_to(stage)),'asset_sha256':asset['sha256']}
            ch.put_json(stage/'runtime.json',receipt)
            stage.rename(target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    model=fetch(spec['model'],base/'Cache',lambda n,t:progress('downloading_model',n,t))
    # The model remains in its verified content-addressed cache, never in the ZIP.
    return {'runtime':str(target),'model':str(model),'archive':str(archive),'platform':key}


def verify(config):
    target=Path(config['runtime']);ch.regular(target)
    spec=lock()
    archive=Path(config['archive']);asset=spec['runtimes'].get(config['platform'])
    if not asset or digest(archive)!=asset['sha256']:raise ValueError('runtime_integrity')
    binaries=[]
    for rel,data,mode in archive_files(archive):
        if digest(target/rel)!=hashlib.sha256(data).hexdigest():raise ValueError('runtime_integrity')
        if Path(rel).name=='llama-completion':binaries.append(target/rel)
    if len(binaries)!=1:raise ValueError('runtime_integrity')
    binary=binaries[0]
    model=Path(config['model'])
    if digest(model)!=spec['model']['sha256']:raise ValueError('runtime_integrity')
    return binary,model


class LocalModel:
    def __init__(self,config,task):
        self.binary,self.model=verify(config)
        self.task=task;self.calls=0;self.metrics=[]

    def ask(self,system,user,schema):
        # Fixed executable and arguments, never a shell or model-proposed code.
        self.calls+=1
        prompt=self.task/('prompt-'+str(self.calls)+'.txt')
        ch.write(prompt,('<|im_start|>system\n'+system+'<|im_end|>\n<|im_start|>user\n'+user+'<|im_end|>\n<|im_start|>assistant\n').encode(),True)
        grammar=self.task/('schema-'+str(self.calls)+'.json');ch.put_json(grammar,schema,True)
        profile=performance.PROFILE
        command=[str(self.binary),'-m',str(self.model),'-f',str(prompt),'-n','1024','-c',str(profile['context']),'-ngl','0',
                 '-b',str(profile['batch']),'-ub',str(profile['ubatch']),'-t',str(profile['threads']),'-tb',str(profile['threads']),
                 '--device','none','--no-op-offload','--no-kv-offload','--no-repack',
                 '--temp','0','--seed','42','--no-display-prompt','--no-conversation','--simple-io',
                 '--json-schema-file',str(grammar)]
        # All model output/logs remain inside this offline private job.
        output=self.task/('inference-'+str(self.calls)+'.out')
        self.metrics.append(performance.inference(command,output,self.task/('inference-'+str(self.calls)+'.log')))
        text=ch.read(output,2*1024*1024).decode('utf-8',errors='strict').strip()
        start=text.find('{');end=text.rfind('}')
        if start<0 or end<start:raise ValueError('local_inference_invalid')
        result=json.loads(text[start:end+1])
        ch.put_json(self.task/('response-'+str(self.calls)+'.json'),result,True)
        return result
