"""Checked package copying and explicit install plans; importing never installs."""
import hashlib,json,os,shutil,stat,tempfile,sys
from pathlib import Path,PurePosixPath,PureWindowsPath
VERSION='0.11.0-dev'

def verify_tree(root,expected=None):
    root=Path(root);raw=(root/'release.json').read_bytes()
    if expected and hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('package_check_failed')
    manifest=json.loads(raw);files=manifest.get('files');seen=set()
    if manifest.get('version')!=VERSION or not isinstance(files,dict) or not 1<=len(files)<=25000:raise ValueError('package_check_failed')
    for name,digest in files.items():
        p=PurePosixPath(name)
        if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or name.casefold() in seen:raise ValueError('package_check_failed')
        seen.add(name.casefold());source=root.joinpath(*p.parts)
        if any(x.is_symlink() for x in (source,*source.parents)):raise ValueError('package_check_failed')
        s=source.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>64*1024*1024 or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('package_check_failed')
    actual={str(p.relative_to(root)).replace('\\','/') for p in root.rglob('*') if p.is_file() and p.name!='release.json'}
    if actual!=set(files):raise ValueError('package_check_failed')
    return manifest

def copy_verified(source,parent,expected):
    source=Path(source);parent=Path(parent);manifest=verify_tree(source,expected)
    target=parent/VERSION
    if target.exists():
        if verify_tree(target,expected)['files']!=manifest['files']:raise ValueError('version_conflict_preserved')
        return target
    parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.install-',dir=parent))
    try:
        for name in manifest['files']:
            dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,dest)
        shutil.copy2(source/'release.json',stage/'release.json');verify_tree(stage,expected)
        target=parent/VERSION
        if target.exists():
            if verify_tree(target,expected)['files']!=manifest['files']:raise ValueError('version_conflict_preserved')
            return target
        stage.rename(target);return target
    finally:
        if stage.exists():shutil.rmtree(stage)

def qualification(root,test=False):
    value=json.loads((Path(root)/'protector/qualification.json').read_text())
    if value.get('release_qualified'):return
    # Only CI developers can explicitly request a test install. The public Skill
    # never supplies this flag, and the original user machine is never a target.
    if test and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted':return
    raise ValueError('platform_validation_pending')

def install_plan(platform,identity,architecture):
    if platform not in ('darwin','win32'):raise ValueError('unsupported_platform')
    if platform=='darwin':
        if architecture not in ('arm64','x86_64'):raise ValueError('unsupported_platform')
        base=PurePosixPath('/Library/Application Support/PrivacyProtector');scope='User-'+str(identity)
        return {'platform':platform,'base':str(base),'app':str(base/'App'/VERSION),'state':str(base/scope),
                'work':str(base/'Workers'/scope),'socket_dir':'/private/var/run/privacy-protector-'+str(identity),
                'service':'org.privacyprotector.user'+str(identity),'python':'runtime-macos-'+architecture+'/bin/python3'}
    if architecture.lower() not in ('amd64','x86_64'):raise ValueError('windows_x64_required')
    # Do not trust an Agent-supplied ProgramData environment variable for a SYSTEM service.
    if sys.platform=='win32':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,0x23,None,0,buffer)!=0:raise ValueError('protection_unavailable')
        base=PureWindowsPath(buffer.value)/'PrivacyProtector'
    else:base=PureWindowsPath('C:/ProgramData/PrivacyProtector')  # Non-Windows plan tests only.
    return {'platform':platform,'base':str(base),'app':str(base/'App'/VERSION),'state':str(base/'State'),
            'service':'PrivacyProtector','python':'runtime/python.exe'}
