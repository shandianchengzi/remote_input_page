# 注册 Remote Input 为开机自启任务（Task Scheduler）
# 需要以管理员权限运行

$taskName = "RemoteInput"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = (Get-Command python).Source
$scriptPath = Join-Path $scriptDir "remote_input.py"

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建任务
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "$scriptPath --auth --token shandianchengzi" `
    -WorkingDirectory $scriptDir

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Remote Input - 手机远程输入工具 (开机自启)"

Write-Host "已注册开机自启任务: $taskName"
Write-Host "端口: 8080"
Write-Host "Token: shandianchengzi"
Write-Host ""
Write-Host "管理方式:"
Write-Host "  查看任务: Get-ScheduledTask -TaskName $taskName"
Write-Host "  手动启动: Start-ScheduledTask -TaskName $taskName"
Write-Host "  停止任务: Stop-ScheduledTask -TaskName $taskName"
Write-Host "  删除任务: Unregister-ScheduledTask -TaskName $taskName"
