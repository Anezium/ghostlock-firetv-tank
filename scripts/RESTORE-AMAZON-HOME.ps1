param([string]$Serial = $env:TANK_SERIAL)

$ErrorActionPreference = 'Stop'
$adbPath = if ($env:ADB) { $env:ADB } else { 'adb' }
if (-not $Serial) {
    $Serial = (& $adbPath devices) |
        Select-String '^\S+\s+device$' |
        ForEach-Object { ($_.Line -split '\s+')[0] } |
        Select-Object -First 1
}
if (-not $Serial) { throw 'Pass -Serial or set TANK_SERIAL (see: adb devices)' }
$stickSerial = $Serial
foreach ($component in @(
    'com.amazon.tv.launcher',
    'com.amazon.tv.launcher/.ui.HomeActivity_vNext',
    'com.amazon.firehomestarter'
)) {
    & $adbPath -s $stickSerial shell "su -c 'pm enable $component'"
    if ($LASTEXITCODE -ne 0) { throw "Unable to restore $component" }
}
& $adbPath -s $stickSerial shell input keyevent 224
& $adbPath -s $stickSerial shell am start -n com.amazon.tv.launcher/.ui.HomeActivity_vNext
if ($LASTEXITCODE -ne 0) { throw 'Unable to open Amazon Home' }
Write-Output 'Amazon Home restored. LeanbackOnFire remains installed; OTA blocking is unchanged.'
