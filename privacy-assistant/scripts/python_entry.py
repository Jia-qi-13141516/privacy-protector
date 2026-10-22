"""Use the bundled pure-Python table libraries on macOS without a pip step."""
import runpy,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'runtime/Lib/site-packages'))
script=Path(sys.argv[1]).resolve()
if root not in script.parents:raise SystemExit(2)
sys.argv=sys.argv[1:];runpy.run_path(str(script),run_name='__main__')
