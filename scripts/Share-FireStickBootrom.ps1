param([ValidatePattern('^[0-9a-fA-F]{4}:[0-9a-fA-F]{4}$')][string]$HardwareId = '0e8d:0003')
$ErrorActionPreference = 'Stop'
$analysis = Join-Path (Split-Path -Parent $PSScriptRoot) 'analysis'
New-Item -ItemType Directory -Force -Path $analysis | Out-Null
$resultPath = Join-Path $analysis ('usbipd-share-' + $HardwareId.Replace(':','-') + '.log')
try {
    $process = Start-Process -FilePath 'C:/Program Files/usbipd-win/usbipd.exe' -ArgumentList @('bind','--hardware-id',$HardwareId) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput ($resultPath + '.stdout') -RedirectStandardError ($resultPath + '.stderr')
    $commandExitCode = $process.ExitCode
    @{ ExitCode = $commandExitCode; Finished = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit $commandExitCode
} catch {
    Add-Content -LiteralPath $resultPath -Value $_.Exception.Message -Encoding UTF8
    exit 1
}
