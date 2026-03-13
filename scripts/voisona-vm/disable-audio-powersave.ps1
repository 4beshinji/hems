# Disable Windows audio power saving features
# Run as Administrator once. Prevents audio device from sleeping during idle.
#
# Usage: Run PowerShell as Admin, then:
#   .\disable-audio-powersave.ps1

Write-Host "=== HEMS: Disable Audio Power Saving ==="
Write-Host ""

# 1. Disable USB Selective Suspend (prevents USB audio devices from sleeping)
Write-Host "[1/4] Disabling USB Selective Suspend..."
powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /SETDCVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
Write-Host "  Done."

# 2. Set High Performance power plan (prevents CPU/timer throttling)
Write-Host "[2/4] Activating High Performance power plan..."
$highPerf = powercfg /LIST | Select-String "High performance" | ForEach-Object {
    if ($_ -match '([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})') {
        $matches[1]
    }
}
if ($highPerf) {
    powercfg /SETACTIVE $highPerf
    Write-Host "  Activated: $highPerf"
} else {
    Write-Host "  High Performance plan not found. Creating..."
    powercfg /DUPLICATESCHEME 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
    $highPerf = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    powercfg /SETACTIVE $highPerf
    Write-Host "  Created and activated."
}

# 3. Disable display and sleep timeouts (VM should stay awake)
Write-Host "[3/4] Disabling display/sleep timeouts..."
powercfg /CHANGE monitor-timeout-ac 0
powercfg /CHANGE standby-timeout-ac 0
powercfg /CHANGE hibernate-timeout-ac 0
Write-Host "  Monitor/standby/hibernate timeouts set to Never."

# 4. Disable audio device power management via registry
Write-Host "[4/4] Disabling audio device power management..."
$audioDevices = Get-PnpDevice -Class AudioEndpoint -Status OK -ErrorAction SilentlyContinue
if ($audioDevices) {
    foreach ($dev in $audioDevices) {
        $instanceId = $dev.InstanceId
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Enum\$instanceId\Device Parameters"
        if (Test-Path $regPath) {
            # ConservationIdleTime = 0 disables idle timeout
            Set-ItemProperty -Path $regPath -Name "ConservationIdleTime" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $regPath -Name "IdleInWorkingState" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $regPath -Name "PerformanceIdleTime" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Write-Host "  Disabled power management for: $($dev.FriendlyName)"
        }
    }
} else {
    Write-Host "  No audio endpoint devices found (OK if using SPICE virtual audio)."
}

Write-Host ""
Write-Host "=== Done. Restart may be required for registry changes to take effect. ==="

# Apply current power scheme changes
powercfg /SETACTIVE SCHEME_CURRENT
