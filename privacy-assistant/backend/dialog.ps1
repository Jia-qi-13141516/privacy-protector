param([string]$InputPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$request=Get-Content -LiteralPath $InputPath -Raw -Encoding UTF8 | ConvertFrom-Json
function Save-Reply($value) {
  $json=ConvertTo-Json -InputObject $value -Depth 12 -Compress
  [IO.File]::WriteAllText($OutputPath,$json,(New-Object Text.UTF8Encoding($false)))
}
if ($request.mode -eq 'file' -or $request.mode -eq 'document_file') {
  $d=New-Object Windows.Forms.OpenFileDialog
  $d.Title='选择需要处理的原表 · 文件只在本地读取'
  $d.Filter='表格文件 (*.xlsx;*.csv)|*.xlsx;*.csv'
  if ($request.mode -eq 'document_file') { $d.Title='选择文档 · 原件只在本地读取'; $d.Filter='文档 (*.docx;*.txt;*.md;*.pdf)|*.docx;*.txt;*.md;*.pdf' }
  $d.Multiselect=$false
  if ($d.ShowDialog() -eq 'OK') { Save-Reply @{path=$d.FileName} } else { Save-Reply @{cancelled=$true} }
  exit
}
if ($request.mode -in @('document_terms','document_review','document_options','document_confirm')) {
  $f=New-Object Windows.Forms.Form
  $f.Text='隐私保护Skill · 文档保护';$f.Size=New-Object Drawing.Size(900,720)
  $f.StartPosition='CenterScreen';$f.Font=New-Object Drawing.Font('Microsoft YaHei UI',11)
  $f.Tag=@{cancelled=$true}
  $label=New-Object Windows.Forms.Label
  $label.Location=New-Object Drawing.Point(24,20);$label.Size=New-Object Drawing.Size(840,80)
  $f.Controls.Add($label)
  $box=New-Object Windows.Forms.TextBox
  $box.Multiline=$true;$box.ScrollBars='Both';$box.WordWrap=$true
  $box.Location=New-Object Drawing.Point(24,108);$box.Size=New-Object Drawing.Size(835,450)
  $box.MaxLength=200000;$box.Text=[string]$request.text
  $f.Controls.Add($box)
  $check=New-Object Windows.Forms.CheckBox
  $check.Location=New-Object Drawing.Point(24,578);$check.Size=New-Object Drawing.Size(420,32)
  $check.Text='在本地恢复身份信息（默认保留代号）';$check.Checked=$false
  $f.Controls.Add($check);$check.Visible=$false
  $format=New-Object Windows.Forms.ComboBox
  $format.Location=New-Object Drawing.Point(24,578);$format.Size=New-Object Drawing.Size(240,32)
  $format.DropDownStyle='DropDownList';[void]$format.Items.AddRange('Word 正文','文本');$format.SelectedIndex=0
  $f.Controls.Add($format);$format.Visible=$false
  $yes=New-Object Windows.Forms.Button
  $yes.Location=New-Object Drawing.Point(590,620);$yes.Size=New-Object Drawing.Size(265,42)
  $f.Controls.Add($yes)
  $no=New-Object Windows.Forms.Button
  $no.Text='取消';$no.Location=New-Object Drawing.Point(445,620);$no.Size=New-Object Drawing.Size(120,42)
  $no.Add_Click({$f.Close()});$f.Controls.Add($no)
  switch ($request.mode) {
    'document_terms' {
      $label.Text='仅处理获准使用 AI 的普通工作材料；标密材料不得进入此流程。请补充需要隐藏的姓名、机构、地点、事件短语，每行一个。自动规则不能覆盖全部隐私。'
      $yes.Text='确认材料适用，生成脱敏稿'
      $yes.Add_Click({$terms=@($box.Lines | ForEach-Object { $_.Trim() } | Where-Object { $_ });$f.Tag=@{confirmed=$true;terms=$terms};$f.Close()})
    }
    'document_review' {
      $label.Text='这是即将提供给 Agent 的完整正文。请检查并删除仍可识别身份的细节；不要修改 ⟦PVT_…⟧ 代号。确认前不会提供给 AI。'
      $yes.Text='已检查，允许提供脱敏稿'
      $yes.Add_Click({$f.Tag=@{confirmed=$true;text=$box.Text};$f.Close()})
    }
    'document_options' {
      $label.Text='是否在本地恢复身份？摘要可能省略代号；下一步请核对人与事件的对应关系。'
      $box.Visible=$false;$check.Visible=$true;$check.Location=New-Object Drawing.Point(24,125)
      $yes.Text='继续核验结果'
      $yes.Add_Click({$f.Tag=@{confirmed=$true;restore=$check.Checked};$f.Close()})
    }
    'document_confirm' {
      $label.Text='请核对事实、遗漏和身份对应关系。程序不能判断 AI 是否改变了原意；确认后生成干净正文，不保留原批注、附件或复杂版式。'
      $box.ReadOnly=$true;$format.Visible=$true;$yes.Text='已核对，生成结果文件'
      $yes.Add_Click({$ext=if ($format.SelectedIndex -eq 0) {'.docx'} else {'.txt'};$f.Tag=@{confirmed=$true;extension=$ext};$f.Close()})
    }
  }
  [void]$f.ShowDialog();Save-Reply $f.Tag;exit
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
