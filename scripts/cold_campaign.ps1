param(
    [string]$Serial = '192.168.1.172:5555',
    [int]$Count = 8,
    [int]$Attempts = 3
)
$S = $Serial
for ($i = 1; $i -le $Count; $i++) {
    adb -s $S reboot 2>&1 | Out-Null
    Start-Sleep -Seconds 8
    $on = $false
    for ($k = 0; $k -lt 60; $k++) {
        adb connect $S 2>&1 | Out-Null
        $dev = adb devices 2>$null | Select-String ('^' + [regex]::Escape($S) + '\s+device')
        if ($dev) { $on = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $on) { Write-Output ("cold {0}: device never came back" -f $i); break }
    $out = (python gl_root.py --serial $S --attempts $Attempts --cmd "id -u" 2>&1 | Out-String)
    $m = [regex]::Matches($out, 'attempt (\d+)/' + $Attempts + ' \.\.\. (ROOT|fail)')
    $seq = ($m | ForEach-Object { $_.Groups[1].Value + ':' + $_.Groups[2].Value }) -join ' '
    $reb = if ($out -match '\[device rebooted\]') { ' RBT' } else { '' }
    $ok = if ($out -match 'command output') { 'OK' } else { 'FAIL' }
    Write-Output ("cold {0}: {1}{2} => {3}" -f $i, $seq, $reb, $ok)
}
