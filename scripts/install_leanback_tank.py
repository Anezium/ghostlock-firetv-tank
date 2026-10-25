"""Install the official launcher on the identified tank; collect bounded diagnostics."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from tank_serial import adb_binary, resolve_serial

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/launchers'
ADB = adb_binary()
SERIAL = resolve_serial()
PKG = 'com.amazon.tv.leanbacklauncher'

def adb(*args, timeout=30, binary=False):
    result = subprocess.run([ADB, '-s', SERIAL, *args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode('utf-8', errors='replace'))
    return result.stdout if binary else result.stdout.decode('utf-8', errors='replace').strip()

def shell(command, timeout=30):
    return adb('shell', command, timeout=timeout)

def snapshot(name):
    for kind in ('activity activities', 'window windows', 'package ' + PKG):
        text = shell('dumpsys ' + kind)
        (OUT / (name + '-' + kind.split()[0] + '.txt')).write_text(text, encoding='utf-8')
    windows = (OUT / (name + '-window.txt')).read_text(encoding='utf-8')
    print('\n'.join(line.strip() for line in windows.splitlines() if 'mCurrentFocus' in line or 'mFocusedApp' in line), flush=True)
    try:
        png = adb('exec-out', 'screencap -p', binary=True)
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Invalid PNG stream')
        (OUT / (name + '.png')).write_bytes(png)
        print('SCREENSHOT ' + str(OUT / (name + '.png')), flush=True)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print('SCREENSHOT_UNAVAILABLE ' + str(exc), flush=True)

phase = sys.argv[1]
if phase == 'verify':
    print('WAITING_FOR_REBOOT', flush=True)
    adb('wait-for-device', timeout=120)
if shell('getprop ro.product.device') != 'tank' or shell('getprop ro.build.version.sdk') != '22':
    raise SystemExit('Unexpected device or Android version')
if 'uid=0(root)' not in shell("su -c 'id'"):
    raise SystemExit('Root not available')

if phase == 'install':
    for cmd, name in [('pm list packages', 'packages-before'), ('pm list packages -d', 'disabled-before'),
                      ('dumpsys package com.amazon.tv.launcher', 'amazon-home-before'),
                      ('dumpsys package com.amazon.firehomestarter', 'home-starter-before')]:
        (OUT / (name + '.txt')).write_text(shell(cmd), encoding='utf-8')
    apk = OUT / 'LeanbackOnFire-official.apk'
    (OUT / 'installed-apk.json').write_text(json.dumps({
        'source': 'https://github.com/tsynik/LeanbackLauncher/releases/download/v1.63/LeanbackOnFire_v1.63-release.apk',
        'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'bytes': apk.stat().st_size,
        'serial': SERIAL, 'version': '1.63', 'minSdk': 22,
    }, indent=2), encoding='utf-8')
    print(adb('install', '-r', str(apk), timeout=180), flush=True)
    shell('input keyevent 224')
    print(shell('am start -n ' + PKG + '/.MainActivity'), flush=True)
    time.sleep(5)
    snapshot('first-launch')
    crash = shell('logcat -b crash -d -t 150')
    (OUT / 'first-launch-crash.txt').write_text(crash, encoding='utf-8')
    print(crash[-7000:], flush=True)
elif phase == 'snapshot':
    snapshot(sys.argv[2])
elif phase == 'configure':
    try:
        for component in ('com.amazon.firehomestarter', 'com.amazon.tv.launcher/.ui.HomeActivity_vNext'):
            result = shell("su -c 'pm disable " + component + "'")
            print(result, flush=True)
            if 'disabled' not in result:
                raise RuntimeError('Disable did not confirm: ' + component)
        print(shell('am start -a android.intent.action.MAIN -c android.intent.category.HOME'), flush=True)
        shell('input keyevent 3')
        time.sleep(3)
        snapshot('configured-home')
        focus = (OUT / 'configured-home-window.txt').read_text(encoding='utf-8')
        if not any(PKG in line for line in focus.splitlines() if 'mCurrentFocus' in line):
            raise RuntimeError('Home did not focus LeanbackOnFire')
        print(shell('am start -a android.settings.SETTINGS'), flush=True)
        time.sleep(3)
        snapshot('configured-settings')
        shell('input keyevent 3')
        time.sleep(3)
        snapshot('home-from-settings')
    except Exception:
        for component in ('com.amazon.tv.launcher/.ui.HomeActivity_vNext', 'com.amazon.firehomestarter'):
            shell("su -c 'pm enable " + component + "'")
        shell('am start -n com.amazon.tv.launcher/.ui.HomeActivity_vNext')
        raise
elif phase == 'verify':
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if shell('getprop sys.boot_completed', timeout=8) == '1':
                break
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(3)
    else:
        raise SystemExit('Boot not completed')
    shell('input keyevent 224')
    shell('input keyevent 3')
    time.sleep(4)
    windows = shell('dumpsys window windows')
    focus = [line.strip() for line in windows.splitlines() if 'mCurrentFocus' in line]
    if not any(PKG in line for line in focus):
        raise RuntimeError('Home is not LeanbackOnFire: ' + str(focus))
    original = set((OUT / 'packages-before.txt').read_text(encoding='utf-8').splitlines())
    current = set(shell('pm list packages').splitlines())
    if original - current:
        raise RuntimeError('Missing packages: ' + str(original - current))
    before_disabled = set((OUT / 'disabled-before.txt').read_text(encoding='utf-8').splitlines())
    disabled = set(shell('pm list packages -d').splitlines())
    if not before_disabled <= disabled:
        raise RuntimeError('Previous debloat state changed')
    print(shell('am start -n com.amazon.tv.launcher/.ui.MainSettingsActivity'), flush=True)
    time.sleep(3)
    windows = shell('dumpsys window windows')
    settings_focus = [line.strip() for line in windows.splitlines() if 'mCurrentFocus' in line]
    if not any('MainSettingsActivity' in line for line in settings_focus):
        raise RuntimeError('Amazon Settings did not open: ' + str(settings_focus))
    shell('input keyevent 3')
    time.sleep(3)
    snapshot('verified-home')
    crash = shell('logcat -b crash -d -t 150')
    (OUT / 'verified-crash.txt').write_text(crash, encoding='utf-8')
    report = {'serial': SERIAL, 'boot_completed': True, 'home': focus,
              'settings': settings_focus, 'missing_original_packages': [],
              'original_debloat_preserved': True, 'disabled_packages': sorted(disabled),
              'root': shell("su -c 'id'"), 'uptime': shell('cat /proc/uptime'),
              'package': shell('dumpsys package ' + PKG),
              'amazon_home_package': shell('dumpsys package com.amazon.tv.launcher')}
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('VERIFIED_HOME_SETTINGS_PACKAGES_ROOT', flush=True)
else:
    raise SystemExit('Unknown phase')
