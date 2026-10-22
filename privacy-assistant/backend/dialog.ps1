param([string]$InputPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$request=Get-Content -LiteralPath $InputPath -Raw -Encoding UTF8 | ConvertFrom-Json
function Save-Reply($value) {
  $json=ConvertTo-Json -InputObject $value -Depth 12 -Compress
  [IO.File]::WriteAllText($OutputPath,$json,(New-Object Text.UTF8Encoding($false)))
}
if ($request.mode -eq 'file') {
  $d=New-Object Windows.Forms.OpenFileDialog
  $d.Title='选择需要处理的原表 · 文件只在本地读取'
  $d.Filter='表格文件 (*.xlsx;*.csv)|*.xlsx;*.csv'
  $d.Multiselect=$false
  if ($d.ShowDialog() -eq 'OK') { Save-Reply @{path=$d.FileName} } else { Save-Reply @{cancelled=$true} }
  exit
}
$form=New-Object Windows.Forms.Form
$form.Text='隐私助手'
$form.Size=New-Object Drawing.Size(820,600)
$form.StartPosition='CenterScreen'
$form.BackColor=[Drawing.Color]::White
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',11)
$form.TopMost=$true
$title=New-Object Windows.Forms.Label
$title.Location=New-Object Drawing.Point(24,20)
$title.Size=New-Object Drawing.Size(750,55)
$form.Controls.Add($title)
$grid=New-Object Windows.Forms.DataGridView
$grid.Location=New-Object Drawing.Point(24,85)
$grid.Size=New-Object Drawing.Size(750,385)
$grid.AllowUserToAddRows=$false
$grid.AllowUserToDeleteRows=$false
$grid.RowHeadersVisible=$false
$grid.AutoSizeColumnsMode='Fill'
$grid.BackgroundColor=[Drawing.Color]::White
$form.Controls.Add($grid)
$ok=New-Object Windows.Forms.Button
$ok.Location=New-Object Drawing.Point(520,490)
$ok.Size=New-Object Drawing.Size(250,42)
$form.Controls.Add($ok)
$cancel=New-Object Windows.Forms.Button
$cancel.Text='取消'
$cancel.Location=New-Object Drawing.Point(380,490)
$cancel.Size=New-Object Drawing.Size(120,42)
$cancel.Add_Click({$form.Close()})
$form.Controls.Add($cancel)
$form.Tag=@{cancelled=$true}
if ($request.mode -eq 'fields') {
  $title.Text="选择本次分析需要的列。身份编号会替换为代号，其余不选的列不会提供给 AI。"
  [void]$grid.Columns.Add('name','原表列名')
  $grid.Columns[0].ReadOnly=$true
  $choices=New-Object Windows.Forms.DataGridViewComboBoxColumn
  $choices.Name='use';$choices.HeaderText='本次用途'
  [void]$choices.Items.AddRange('不提供','身份编号','数值','分类')
  [void]$grid.Columns.Add($choices)
  foreach ($field in $request.fields) {
    $initial=if ($field.kind -eq 'id') {'身份编号'} else {'不提供'}
    [void]$grid.Rows.Add([string]$field.header,$initial)
  }
  $ok.Text='允许提供所选代号数据'
  $ok.Add_Click({
    $grid.EndEdit()
    $map=@{'不提供'='drop';'身份编号'='id';'数值'='number';'分类'='category'}
    $selected=@($grid.Rows | ForEach-Object { $map[[string]$_.Cells[1].Value] })
    if (@($selected | Where-Object { $_ -eq 'id' }).Count -ne 1) {
      [void][Windows.Forms.MessageBox]::Show('请选择且只选择一个身份编号列。','隐私助手');return
    }
    $form.Tag=@{choices=$selected};$form.Close()
  })
} elseif ($request.mode -eq 'preview') {
  $title.Text="本地回填结果：共 $($request.rows.Count) 条。核对身份与结果后，生成导入文件。"
  $grid.ReadOnly=$true
  if ($request.rows.Count -gt 0) {
    $names=@($request.rows[0].PSObject.Properties.Name)
    foreach ($name in $names) {[void]$grid.Columns.Add($name,$name)}
    foreach ($row in $request.rows) {
      $values=@($names | ForEach-Object {[string]$row.$_})
      [void]$grid.Rows.Add([object[]]$values)
    }
  }
  $ok.Text='确认并生成导入文件'
  $ok.Add_Click({$form.Tag=@{confirmed=$true};$form.Close()})
} else {exit 2}
[void]$form.ShowDialog()
Save-Reply $form.Tag
