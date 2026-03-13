# Register Windows Scheduled Task for daily VoiSona restart
# Run as Administrator once.
#
# Usage: Run PowerShell as Admin, then:
#   .\setup-scheduled-task.ps1

$TaskName = "HEMS-VoiSona-DailyRestart"
$ScriptPath = "$PSScriptRoot\restart-voisona.ps1"
$RestartTime = "04:00"  # 4:00 AM daily

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -Daily -At $RestartTime

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false

$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "HEMS: Daily restart of VoiSona Talk to prevent synthesis degradation"

Write-Host ""
Write-Host "Scheduled task '$TaskName' registered."
Write-Host "  Trigger: Daily at $RestartTime"
Write-Host "  Script:  $ScriptPath"
Write-Host ""
Write-Host "To verify:  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To run now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$TaskName'"
