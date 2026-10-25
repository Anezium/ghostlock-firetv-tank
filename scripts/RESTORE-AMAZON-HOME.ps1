$ErrorActionPreference = 'Stop'
$adbPath = 'C:/Users/saim2/AppData/Local/Android/Sdk/platform-tools/adb.exe'
$stickSerial = 'G070L81694972B80'
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
