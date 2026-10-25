param([string]$Serial = $env:TANK_SERIAL)

$adb = if ($env:ADB) { $env:ADB } else { 'adb' }
if (-not $Serial) {
    $Serial = (& $adb devices) |
        Select-String '^\S+\s+device$' |
        ForEach-Object { ($_.Line -split '\s+')[0] } |
        Select-Object -First 1
}
if (-not $Serial) { throw 'Pass -Serial or set TANK_SERIAL (see: adb devices)' }
$packages = @(
    # Les mises a jour OTA restent bloquees pour proteger l'installation root.
    'com.amazon.bueller.photos',
    'com.amazon.ftv.screensaver',
    'com.amazon.alexashopping',
    'com.amazon.shoptv.client',
    'com.amazon.shoptv.firetv.client',
    'com.amazon.kor.demo'
)
foreach ($package in $packages) {
    & $adb -s $Serial shell "su -c 'pm enable --user 0 $package'"
}
