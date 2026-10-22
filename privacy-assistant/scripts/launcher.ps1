Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$form = New-Object Windows.Forms.Form
$form.Text = '隐私助手'
$form.Size = New-Object Drawing.Size(480,390)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI',11)
$form.BackColor = [Drawing.Color]::White
$title = New-Object Windows.Forms.Label
$title.Text = '开始一个受保护的任务'
$title.Location = New-Object Drawing.Point(26,25)
$title.Size = New-Object Drawing.Size(410,36)
$title.Font = New-Object Drawing.Font('Microsoft YaHei UI',16,[Drawing.FontStyle]::Bold)
$form.Controls.Add($title)
$note = New-Object Windows.Forms.Label
$note.Text = "原表留在本地。联网 AI 只接触你允许提供的资料。`n首次使用会先检查 Windows 沙盒。"
$note.Location = New-Object Drawing.Point(28,76)
$note.Size = New-Object Drawing.Size(410,55)
$form.Controls.Add($note)
$start = New-Object Windows.Forms.Button
$start.Text = '新建表格任务'
$start.Location = New-Object Drawing.Point(28,150)
$start.Size = New-Object Drawing.Size(400,44)
$start.Add_Click({$form.Tag='new';$form.Close()})
$form.Controls.Add($start)
$demo = New-Object Windows.Forms.LinkLabel
$demo.Text = '第一次使用？先试一次虚构演示'
$demo.Location = New-Object Drawing.Point(28,300)
$demo.Size = New-Object Drawing.Size(400,28)
$demo.Add_Click({$form.Tag='demo';$form.Close()})
$form.Controls.Add($demo)
$finish = New-Object Windows.Forms.Button
$finish.Text = '已有 AI 结果，回填导入文件'
$finish.Location = New-Object Drawing.Point(28,210)
$finish.Size = New-Object Drawing.Size(400,44)
$finish.Add_Click({$form.Tag='finish';$form.Close()})
$form.Controls.Add($finish)
$form.Tag='cancel'
[void]$form.ShowDialog()
[Console]::Write($form.Tag)
