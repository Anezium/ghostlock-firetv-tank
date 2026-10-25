param([int]$DurationSeconds = 300)
$ErrorActionPreference = 'Stop'
$usbipdPath = 'C:/Program Files/usbipd-win/usbipd.exe'
$logPath = Join-Path $PSScriptRoot '../analysis/firestick-usb-detection.jsonl'
$deadline = (Get-Date).AddSeconds($DurationSeconds)
$previousState = ''
function Write-DetectionEvent($eventData) {
    $line = $eventData | ConvertTo-Json -Compress -Depth 6
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    Write-Output $line
}
Write-DetectionEvent @{ Time = (Get-Date).ToString('o'); Event = 'WAITING'; DurationSeconds = $DurationSeconds; Mode = 'USB enumeration only; no device writes' }
while ((Get-Date) -lt $deadline) {
    $rawState = & $usbipdPath state
    if ($LASTEXITCODE -ne 0) { throw 'usbipd state failed' }
    $state = ($rawState -join "`n") | ConvertFrom-Json
    $targets = @($state.Devices | Where-Object { $_.BusId -and $_.InstanceId -match 'VID_(0E8D|1949)' } | Select-Object BusId, Description, InstanceId)
    $signature = ConvertTo-Json -InputObject $targets -Compress -Depth 5
    if ($signature -ne $previousState) {
        Write-DetectionEvent @{ Time = (Get-Date).ToString('o'); Event = 'USB_STATE'; Devices = $targets }
        $previousState = $signature
    }
    Start-Sleep -Milliseconds 400
}
Write-DetectionEvent @{ Time = (Get-Date).ToString('o'); Event = 'MONITOR_FINISHED' }
