"""Runs the native wizard only after a real offline-worker probe passes."""
import json,os,subprocess,sys,base64
from pathlib import Path

def main():
    if sys.platform!='win32' or Path(__file__).parent!=Path(r'C:\PrivacyUI'):return 2
    probe=subprocess.run([sys.executable,'-I','-B',r'C:\PrivacySkill\scripts\run_local.py','--input',r'C:\missing-privacy-input','--policy',r'C:\missing-privacy-policy','--out',r'C:\missing-privacy-output'],capture_output=True,text=True,timeout=30)
    try:ok=json.loads(probe.stdout).get('code')=='input_rejected'
    except Exception:ok=False
    if not ok:return 2
    source=Path(r'C:\PrivacyUI\wizard_ui.ps1').read_text(encoding='utf-8')
    command=base64.b64encode(source.encode('utf-16le')).decode()
    # Payload is fixed packaged UI code, never model-generated script or spreadsheet.
    subprocess.run(['powershell.exe','-NoProfile','-STA','-EncodedCommand',command],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    handoff=Path(r'C:\PrivacyTask\handoff.json')
    if not handoff.exists():handoff.write_text('{"status":"cancelled"}',encoding='utf-8')
    # This shutdown is ONLY reachable inside the verified offline Windows guest.
    subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/shutdown.exe'),'/s','/t','0'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return 0
if __name__=='__main__':sys.exit(main())
