"""Protected setup entry. No fallback to the former same-user background worker."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protector'))
import bootstrap
run=bootstrap.run
if __name__=='__main__':
    import runpy
    runpy.run_path(str(Path(bootstrap.__file__)),run_name='__main__')
