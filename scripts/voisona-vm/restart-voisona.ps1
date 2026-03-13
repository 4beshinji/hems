# VoiSona Talk daily restart script
# Schedule via Windows Task Scheduler:
#   Action: powershell.exe -ExecutionPolicy Bypass -File C:\hems\restart-voisona.ps1
#   Trigger: Daily at 04:00 (or preferred time)
#
# Usage: .\restart-voisona.ps1

$ProcessName = "VoiSona Talk"
$ExePath = "${env:LOCALAPPDATA}\Programs\VoiSona Talk\VoiSona Talk.exe"

# Find and stop VoiSona Talk
$proc = Get-Process -Name "VoiSona Talk" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Stopping $ProcessName (PID: $($proc.Id))..."
    $proc | Stop-Process -Force
    Start-Sleep -Seconds 3
} else {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $ProcessName not running."
}

# Start VoiSona Talk
if (Test-Path $ExePath) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting $ProcessName..."
    Start-Process -FilePath $ExePath
    Start-Sleep -Seconds 10
    $newProc = Get-Process -Name "VoiSona Talk" -ErrorAction SilentlyContinue
    if ($newProc) {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $ProcessName started (PID: $($newProc.Id))."
    } else {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] WARNING: $ProcessName did not start."
    }
} else {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $ExePath not found."
    # Try alternate paths
    $altPaths = @(
        "C:\Program Files\VoiSona Talk\VoiSona Talk.exe",
        "C:\Program Files (x86)\VoiSona Talk\VoiSona Talk.exe"
    )
    foreach ($alt in $altPaths) {
        if (Test-Path $alt) {
            Write-Host "  Found at: $alt"
            Start-Process -FilePath $alt
            break
        }
    }
}
