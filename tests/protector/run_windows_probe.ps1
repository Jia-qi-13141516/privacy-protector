$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Disposable CI only' }
$python=(Get-Command python).Source
$script=Join-Path $PSScriptRoot 'windows_native_probe.py'
$report=Join-Path $env:RUNNER_TEMP 'windows-native.json'
$log=Join-Path $env:RUNNER_TEMP 'windows-probe.log'
$wrapper=Join-Path $env:RUNNER_TEMP 'pp-system-probe.cmd'
# No credentials are written here; the Python probe creates a random disposable user.
@"
@echo off
set GITHUB_ACTIONS=true
set RUNNER_ENVIRONMENT=github-hosted
"$python" -I -B "$script" "$report" >"$log" 2>&1
"@ | Set-Content -LiteralPath $wrapper -Encoding ASCII
$task='PrivacyProtectorProbe-'+[guid]::NewGuid().ToString('N')
try {
 $action=New-ScheduledTaskAction -Execute "$env:WINDIR\System32\cmd.exe" -Argument ('/c "'+$wrapper+'"')
 Register-ScheduledTask -TaskName $task -Action $action -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
 Start-ScheduledTask -TaskName $task
 $deadline=(Get-Date).AddMinutes(3)
 do {
  Start-Sleep -Seconds 2
  $state=(Get-ScheduledTask -TaskName $task).State
 } while ($state -eq 'Running' -and (Get-Date) -lt $deadline)
 if (Test-Path $log) { Get-Content -LiteralPath $log }
 if (-not (Test-Path $report)) { throw ('Windows kernel probe failed: '+(Get-ScheduledTaskInfo -TaskName $task).LastTaskResult) }
 Get-Content -LiteralPath $report
} finally { Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue }
