param(
    [Parameter(Mandatory=$true)][string]$StateDirectory,
    [string]$BusId = '1-7',
    [ValidateRange(1,60)][int]$Minutes = 45
)
$ErrorActionPreference = 'Stop'
$usbipdPath = 'C:/Program Files/usbipd-win/usbipd.exe'
New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
$logPath = Join-Path $StateDirectory 'events.jsonl'
$deadline = (Get-Date).AddMinutes($Minutes)
function Write-SessionEvent([string]$eventName, $details) {
    @{ Time=(Get-Date).ToString('o'); Event=$eventName; Details=$details } | ConvertTo-Json -Compress -Depth 5 | Add-Content -LiteralPath $logPath -Encoding UTF8
}
Write-SessionEvent 'ADMIN_READY' @{ BusId=$BusId; Deadline=$deadline.ToString('o'); ProcessId=$PID }
Set-Content -LiteralPath (Join-Path $StateDirectory 'READY') -Value $PID -Encoding UTF8
$attempted = @{}
while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath (Join-Path $StateDirectory 'STOP'))) {
    try {
        $rawState = & $usbipdPath state
        if ($LASTEXITCODE -ne 0) { throw 'USB state query failed' }
        $state = ($rawState -join "`n") | ConvertFrom-Json
        $device = $state.Devices | Where-Object { $_.BusId -eq $BusId } | Select-Object -First 1
        # Only this physical port, and only the Android/Amazon/MediaTek USB
        # vendor families used by this Fire TV's bootloader and recovery.
        if ($device -and $device.InstanceId -match '^USB\\VID_(0BB4|1949|18D1|0E8D)&PID_' -and -not $device.PersistedGuid) {
            $key = $device.InstanceId
            if (-not $attempted.ContainsKey($key)) {
                $attempted[$key] = $true
                $prefix = Join-Path $StateDirectory ('bind-' + (Get-Date -Format 'HHmmssfff'))
                $process = Start-Process -FilePath $usbipdPath -ArgumentList @('bind','--busid',$BusId) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput ($prefix + '.stdout') -RedirectStandardError ($prefix + '.stderr')
                Write-SessionEvent 'BIND_RESULT' @{ BusId=$BusId; InstanceId=$key; ExitCode=$process.ExitCode; LogPrefix=$prefix }
            }
        }
    } catch {
        Write-SessionEvent 'ERROR' $_.Exception.Message
    }
    Start-Sleep -Seconds 1
}
Write-SessionEvent 'ADMIN_SESSION_FINISHED' @{}
