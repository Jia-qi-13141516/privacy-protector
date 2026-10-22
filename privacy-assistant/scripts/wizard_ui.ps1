Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$ErrorActionPreference='Stop'
$task='C:\PrivacyTask'
$private=Join-Path $task 'private'
$mode=(Get-Content 'C:\PrivacyControl\request.json' -Raw | ConvertFrom-Json).mode
$python='C:\PrivacyRuntime\python.exe'
$source=(Get-ChildItem "$private\original.*" | Where-Object Extension -in '.xlsx','.csv' | Select-Object -First 1).FullName
function Worker([string]$action) {
    $reply=& $python -I -B 'C:\PrivacyUI\table_wizard.py' $action $task 2>$null
    if ($LASTEXITCODE -ne 0) {throw '本地检查未通过。请核对表格结构，不要上传原表排错。'}
    return ($reply | ConvertFrom-Json)
}
function Core([string[]]$ExtraArgs) {
    $reply=& $python -I -B 'C:\PrivacySkill\scripts\run_local.py' --input $source --policy "$private\policy.json" @ExtraArgs 2>$null
    if ($LASTEXITCODE -ne 0) {throw '表格核验未通过。可能有重复编号、未知类别、缺失字段或结果改动。原表保持不变。'}
    return ($reply | ConvertFrom-Json)
}
$form=New-Object Windows.Forms.Form
$form.Text='隐私助手 · 本地处理'
$form.Size=New-Object Drawing.Size(800,590)
$form.StartPosition='CenterScreen'
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',11)
$form.BackColor=[Drawing.Color]::White
$label=New-Object Windows.Forms.Label
$label.SetBounds(24,18,730,66)
$form.Controls.Add($label)
$grid=New-Object Windows.Forms.DataGridView
$grid.SetBounds(24,90,730,350)
$grid.AllowUserToAddRows=$false
$grid.AutoSizeColumnsMode='Fill'
$grid.RowHeadersVisible=$false
$form.Controls.Add($grid)
$go=New-Object Windows.Forms.Button
$go.SetBounds(24,464,730,48)
$form.Controls.Add($go)
try {
 if ($mode -eq 'new') {
    [void](Worker 'inspect')
    $schema=Get-Content "$private\schema.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    $label.Text="只选择本次需要的列，其余列默认不提供。`n身份编号会替换成代号；仅处理第一个工作表。"
    [void]$grid.Columns.Add('field','原表列名')
    $grid.Columns['field'].ReadOnly=$true
    $kind=New-Object Windows.Forms.DataGridViewComboBoxColumn
    $kind.Name='kind';$kind.HeaderText='这列怎么用'
    $kind.Items.AddRange(@('不提供','身份编号','数值','分类'))
    [void]$grid.Columns.Add($kind)
    foreach($f in $schema.fields) {
        $value=if($f.kind -eq 'id'){'身份编号'}else{'不提供'}
        [void]$grid.Rows.Add($f.header,$value)
    }
    $go.Text='确认列并在本地处理'
    $go.Add_Click({
      try {
        $go.Enabled=$false;$grid.EndEdit()
        $map=@{'不提供'='drop';'身份编号'='id';'数值'='number';'分类'='category'}
        $choices=@($grid.Rows | ForEach-Object {$map[$_.Cells['kind'].Value]})
        ConvertTo-Json -InputObject @($choices) -Compress | Set-Content "$private\choices.json" -Encoding UTF8
        [void](Worker 'configure')
        [void](Core @('--out',"$task\job"))
        $allowed=[Windows.Forms.MessageBox]::Show('代号数据也可能识别人。是否已确认有权把这份所选数据提供给你使用的 AI？同意后才会放进交换区。','确认用途','YesNo','Question')
        if($allowed -eq 'Yes') {
          Copy-Item "$task\job\private\students.csv" 'C:\PrivacyExchange\数据.csv'
          '数据仅含已获准的列。请先询问老师各代号列的含义与计算规则。保留原有列和 person 代号，不修改原有值。可追加 follow_up（yes/no）及 priority（0到3），或只追加其中一个；可以按明确规则筛选记录。结果保存为UTF-8的结果.csv，保留原有列顺序，再追加新列。不得访问主机原表；姓名学号由本人本地回填。' | Set-Content 'C:\PrivacyExchange\给AI的任务说明.txt' -Encoding UTF8
          '{"status":"ready_for_agent"}' | Set-Content "$task\handoff.json" -Encoding UTF8
        } else {
          '{"status":"local_only"}' | Set-Content "$task\handoff.json" -Encoding UTF8
        }
        $form.Close()
      } catch {[Windows.Forms.MessageBox]::Show('本地检查未通过，请检查字段选择与数据格式。没有授权上传原表。','隐私助手');$go.Enabled=$true}
    })
 } elseif ($mode -eq 'finish') {
    [void](Worker 'preview')
    $preview=@(Get-Content "$private\preview.json" -Raw -Encoding UTF8 | ConvertFrom-Json)
    $label.Text="请核对以下 $($preview.Count) 条记录及结果。`n这是实名本地预览，不会交给 AI；确认后才生成导入文件。"
    foreach($prop in $preview[0].PSObject.Properties.Name) {[void]$grid.Columns.Add($prop,$prop)}
    foreach($item in $preview) {[void]$grid.Rows.Add([object[]]@($item.PSObject.Properties.Value))}
    $grid.ReadOnly=$true;$go.Text="确认这 $($preview.Count) 条记录，生成导入文件"
    $go.Add_Click({
      try {
        $go.Enabled=$false
        $out=Join-Path $task ('import-'+[Guid]::NewGuid().ToString('N'))
        [void](Core @('--mode','prepare-import','--job',"$task\job",'--results',"$private\reviewed.csv",'--import-policy',"$private\import-policy.json",'--out',$out))
        @{status='import_ready';folder=(Split-Path $out -Leaf)} | ConvertTo-Json | Set-Content "$task\handoff.json" -Encoding UTF8
        [Windows.Forms.MessageBox]::Show('导入文件已生成。请在主机本地核对后交给获准业务系统，工具没有自动提交。','隐私助手')
        $form.Close()
      } catch {[Windows.Forms.MessageBox]::Show('结果未通过核验，没有生成导入文件。请检查是否改动原列、重复或使用了非法值。','隐私助手');$go.Enabled=$true}
    })
 } else {throw 'mode'}
 [void]$form.ShowDialog()
} catch {[Windows.Forms.MessageBox]::Show('无法开始本地处理。请确认使用支持的表格与本次任务结果；不要把原表传给模型诊断。','隐私助手')}
