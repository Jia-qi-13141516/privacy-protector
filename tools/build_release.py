from pathlib import Path
import ast,hashlib,json,shutil,zipfile,argparse
parser=argparse.ArgumentParser();parser.add_argument("--archive",action="store_true");args=parser.parse_args()
base=Path(__file__).resolve().parents[1]
(base/'dist').mkdir(exist_ok=True)
archive=base/'dist/privacy-assistant-0.9.0.zip'
r=base/'privacy-assistant'
for name in ('LICENSE','LICENSE-CC-BY-4.0','NOTICE','LICENSING.md','THIRD_PARTY_NOTICES.md'):
 shutil.copy2(base/name,r/name)
if (r/'skill').exists():shutil.rmtree(r/'skill')
shutil.copytree(base/'local-table-privacy',r/'skill',ignore=shutil.ignore_patterns('__pycache__','*.pyc','references','agents','SKILL.md','package_manifest.json'))
assert (r/'runtime').is_dir(), 'Bundled runtime must be present'
(r/'skill/SKILL.md').write_text("---\nname: local-table-privacy\ndescription: 隐私保护 Skill 内置的本地表格引擎。通过包根目录安装器调用，不单独启动旧版沙盒。\n---\n\n本目录保存脱敏、校验、回填和测试代码。安装与使用统一遵循包根目录 SKILL.md；Windows 持久环境由 scripts/auto_setup.py 部署。这里保留的底层兼容入口不属于教师操作流程，不要求用户手工配置策略或部署组件。\n",encoding='utf-8')
# Reuse pure Python libs on macOS as well as the Windows portable runtime.
p=r/'skill/scripts/deidentify.py';s=p.read_text().replace('import sys\n','import sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[2]/"runtime/Lib/site-packages"))\n',1);p.write_text(s)
# Python 3.9 ships on some Macs; correlation() arrived in Python 3.10.
compat = """
def _pearson_compat(x, y):
    mx=statistics.fmean(x);my=statistics.fmean(y)
    dx=[v-mx for v in x];dy=[v-my for v in y]
    numerator=math.fsum(a*b for a,b in zip(dx,dy))
    denominator=math.sqrt(math.fsum(v*v for v in dx))*math.sqrt(math.fsum(v*v for v in dy))
    return max(-1.0,min(1.0,numerator/denominator))

"""
s=p.read_text().replace('def stats(rows, cols):',compat+'def stats(rows, cols):').replace('corr=statistics.correlation(x,y)','corr=(statistics.correlation(x,y) if hasattr(statistics,"correlation") else _pearson_compat(x,y))')
p.write_text(s)
core_files={str(p.relative_to(r/'skill')):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((r/'skill').rglob('*')) if p.is_file() and p.name!='package_manifest.json'}
(r/'skill/package_manifest.json').write_text(json.dumps(core_files,indent=2))
for p in r.rglob('__pycache__'):shutil.rmtree(p)
for p in (r/'scripts').glob('*.py'):ast.parse(p.read_text())
files={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file() and p.name!='release.json' and '__pycache__' not in p.parts}
(r/'release.json').write_text(json.dumps({'version':'0.9.0','files':files},indent=2))
if args.archive:
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(r.rglob('*')):
   if not p.is_file() or '__pycache__' in p.parts:continue
   info=zipfile.ZipInfo('privacy-assistant/'+str(p.relative_to(r)),(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100755 if p.suffix in ('.command',) else 0o100644)<<16
   z.writestr(info,p.read_bytes())
 print(json.dumps({'plugin_version':'0.9.0','files':len(files)+1,'zip_mb':round(Path(archive).stat().st_size/1024**2,1)}))
else:
 print(json.dumps({"source_version":"0.9.0","files":len(files)+1,"release_qualified":False,"archive_created":False}))
