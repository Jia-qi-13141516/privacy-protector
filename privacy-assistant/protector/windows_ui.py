"""Trusted SYSTEM UI in the enrolled desktop session. No material in public files."""
import base64,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from windows_native import root_only
import windows_rpc as rpc,protocol

SCRIPT=r'''
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$r=[Console]::In.ReadToEnd() | ConvertFrom-Json
$out=@{cancelled=$true}
if ($r.mode -eq 'select') {
 $d=New-Object System.Windows.Forms.OpenFileDialog
 $d.Title='选择并保护文件'
 $d.Filter='支持的材料|*.xlsx;*.csv;*.txt;*.md;*.docx;*.pdf'
 if ($d.ShowDialog() -eq 'OK') { $out=@{path=$d.FileName} }
} elseif ($r.mode -eq 'review') {
 $f=New-Object System.Windows.Forms.Form
 $f.Text='Privacy Protector'; $f.Width=840; $f.Height=620; $f.StartPosition='CenterScreen'
 $label=New-Object System.Windows.Forms.Label
 $label.Text='核对结果。确认导出后，结果成为可被其他软件读取的普通文件；原件继续受保护。'
 $label.Dock='Top'; $label.Height=55; $label.Padding=New-Object System.Windows.Forms.Padding(12)
 $text=New-Object System.Windows.Forms.RichTextBox
 $text.Dock='Fill'; $text.ReadOnly=$true; $text.ShortcutsEnabled=$false; $text.DetectUrls=$false; $text.Text=$r.preview
 $buttons=New-Object System.Windows.Forms.FlowLayoutPanel; $buttons.Dock='Bottom'; $buttons.Height=48
 $confirm=New-Object System.Windows.Forms.Button; $confirm.Text='确认并保存'; $confirm.Width=120
 $close=New-Object System.Windows.Forms.Button; $close.Text='暂不导出'; $close.Width=120
 $recover=New-Object System.Windows.Forms.Button; $recover.Text='取回原件'; $recover.Width=120
 $f.Tag='close'
 $confirm.Add_Click({$f.Tag='confirm';$f.Close()})
 $close.Add_Click({$f.Close()})
 $recover.Add_Click({$f.Tag='recover';$f.Close()})
 $buttons.Controls.AddRange(@($confirm,$close,$recover));$f.Controls.AddRange(@($text,$label,$buttons))
 [void]$f.ShowDialog()
 if ($f.Tag -eq 'confirm') {
  $d=New-Object System.Windows.Forms.SaveFileDialog; $d.Title='保存已确认的结果';$d.FileName='处理结果'+$r.extension;$d.OverwritePrompt=$true
  if ($d.ShowDialog() -eq 'OK') { $out=@{destination=$d.FileName} }
 } elseif ($f.Tag -eq 'recover') { $out=@{recover=$true} }
} elseif ($r.mode -eq 'recover') {
 $choice=[System.Windows.Forms.MessageBox]::Show('取回后，其他软件和 Agent 也可能读取原件。是否继续？','取回原件','YesNo','Warning')
 if ($choice -eq 'Yes') { $out=@{confirmed=$true} }
} elseif ($r.mode -eq 'save-original') {
 $d=New-Object System.Windows.Forms.SaveFileDialog;$d.Title='取回原件副本';$d.FileName='取回的原件'+$r.extension
 if ($d.ShowDialog() -eq 'OK') { $out=@{destination=$d.FileName} }
} elseif ($r.mode -eq 'blocked') {
 $choice=[System.Windows.Forms.MessageBox]::Show('任务未通过保护或处理检查，原件不会自动解锁。是否取回原件？','任务未完成','YesNo','Warning')
 if ($choice -eq 'Yes') { $out=@{recover=$true} }
} else { [void][System.Windows.Forms.MessageBox]::Show([string]$r.message,'Privacy Protector') }
$out | ConvertTo-Json -Compress
'''

def dialogue(value):
    # The child retains SYSTEM's identity; raw data is sent only through private pipes.
    encoded=base64.b64encode(SCRIPT.encode('utf-16le')).decode()
    ps=Path(__import__('os').environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    p=subprocess.run([str(ps),'-NoProfile','-STA','-EncodedCommand',encoded],input=json.dumps(value,ensure_ascii=False),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=0x08000000)
    if p.returncode:raise ValueError('ui_unavailable')
    return json.loads(p.stdout.lstrip('\ufeff'))

def main(mode,identifier,sid):
    root_only();protocol.identifier(identifier);pipe=rpc.endpoint(sid,True)
    def call(action,**fields):return rpc.request(pipe,dict(action=action,id=identifier,**fields),private=True)
    def recover(ext):
        if not dialogue({'mode':'recover'}).get('confirmed'):return
        r=call('restore')
        if 'error' in r:
            if ext not in ('.xlsx','.csv','.txt','.md','.docx','.pdf'):raise ValueError('source_changed')
            chosen=dialogue({'mode':'save-original','extension':ext})
            if 'destination' in chosen:r=call('recover',destination=chosen['destination'])
        dialogue({'mode':'message','message':'原件已恢复普通访问。' if 'error' not in r else '原件未取回；已有文件不会被覆盖，保护区中的文件没有删除。'})
    if mode=='select':
        chosen=dialogue({'mode':'select'})
        r=call('select',path=chosen['path']) if 'path' in chosen else call('cancel')
        if r.get('phase')=='blocked':
            detail=call('review')
            if dialogue({'mode':'blocked'}).get('recover'):recover(detail.get('source_extension',''))
        return
    r=call('review')
    if 'preview' not in r:
        if dialogue({'mode':'blocked'}).get('recover'):recover(r.get('source_extension',''))
        return
    result=dialogue(dict(r,mode='review'))
    if 'destination' in result:
        saved=call('confirm',destination=result['destination'])
        dialogue({'mode':'message','message':'结果已保存，原件继续受保护。' if saved.get('phase')=='confirmed' else '结果未保存；请选择未使用的文件名，已有文件不会被覆盖。'})
    elif result.get('recover'):
        if r['phase']=='waiting_for_confirmation':call('cancel')
        recover(r.get('source_extension',''))

if __name__=='__main__':
    try:main(*sys.argv[1:])
    except Exception:sys.exit(2)
