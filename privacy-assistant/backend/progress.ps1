param([string]$StatusPath)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form=New-Object Windows.Forms.Form
$form.Text='隐私助手 · 自动安装'
$form.Size=New-Object Drawing.Size(520,230)
$form.StartPosition='CenterScreen'
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',11)
$form.BackColor=[Drawing.Color]::White
$label=New-Object Windows.Forms.Label
$label.Location=New-Object Drawing.Point(24,24)
$label.Size=New-Object Drawing.Size(460,70)
$label.Text='正在准备。首次安装需要下载运行组件，请保持网络连接。'
$form.Controls.Add($label)
$bar=New-Object Windows.Forms.ProgressBar
$bar.Location=New-Object Drawing.Point(24,110)
$bar.Size=New-Object Drawing.Size(460,24)
$bar.Style='Marquee'
$form.Controls.Add($bar)
$note=New-Object Windows.Forms.Label
$note.Text='窗口关闭后，安装仍会继续；无需输入命令。'
$note.Location=New-Object Drawing.Point(24,150)
$note.Size=New-Object Drawing.Size(460,30)
$form.Controls.Add($note)
$timer=New-Object Windows.Forms.Timer
$timer.Interval=1000
$timer.Add_Tick({
 try {
  $status=Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $label.Text=$status.stage
  if ($status.total -gt 0) {
   $bar.Style='Continuous';$bar.Value=[Math]::Min(100,[int](100*$status.downloaded/$status.total))
  } else {$bar.Style='Marquee'}
  if ($status.stage -in @('安装完成','安装未完成')) {$timer.Stop();$form.Close()}
 } catch {}
})
$timer.Start()
[void]$form.ShowDialog()
$timer.Stop()
