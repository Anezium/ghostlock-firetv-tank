$adb = 'C:/Users/saim2/AppData/Local/Android/Sdk/platform-tools/adb.exe'
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
    & $adb -s G070L81694972B80 shell "su -c 'pm enable --user 0 $package'"
}
