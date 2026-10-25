"""Remove only the applications explicitly approved by the owner; audit the result."""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from tank_serial import adb_binary, resolve_serial

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/app-cleanup-20261025'
OUT.mkdir(exist_ok=True)
ADB = adb_binary()
SERIAL = resolve_serial()
TARGETS = {
    'com.plexapp.android': 'Plex',
    'tv.molotov.app': 'Molotov',
    'com.lagradost.cloudstream3': 'Cloudstream',
    'se.hedekonsult.sparkle': 'Sparkle',
    'com.classyplayerott.player': 'Classy Player',
    'com.esaba.downloader': 'Downloader',
    'com.yablio.sendfilestotv': 'Send Files to TV',
    'com.pokemontv': 'Pokemon TV',
    'com.amazon.bueller.music': 'Amazon Music',
    'com.amazon.minitv.android.app': 'Amazon miniTV',
    'com.amazon.gamehub': 'Amazon Game Hub',
}
CORE = {
    'org.xbmc.kodi', 'com.amazon.tv.leanbacklauncher', 'com.topjohnwu.magisk',
    'com.fluxii.android.mousetoggleforfiretv', 'com.amazon.tv.launcher',
    'com.amazon.avod', 'com.amazon.venezia', 'com.amazon.webview.chromium',
    'com.amazon.tv.ime', 'com.amazon.fireinputdevices', 'com.android.bluetooth',
    'com.amazon.tv.settings.core', 'com.amazon.tv.settings.v2', 'com.amazon.vizzini',
}
assert not CORE.intersection(TARGETS)

def adb(*args, timeout=30):
    result = subprocess.run([ADB, '-s', SERIAL, *args], capture_output=True, timeout=timeout)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
    if result.returncode:
        raise RuntimeError(output)
    return output

def sh(command, timeout=30):
    return adb('shell', command, timeout=timeout)

def packages(flags=''):
    return {line.removeprefix('package:').strip() for line in sh('pm list packages ' + flags).splitlines()
            if line.startswith('package:')}

def free_bytes():
    available, size = sh("su -c '/data/adb/magisk/busybox stat -f -c %a:%S /data'").split(':')
    return int(available) * int(size)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

def focus():
    return [line.strip() for line in sh('dumpsys window windows').splitlines() if 'mCurrentFocus' in line]

phase = sys.argv[1]
if phase == 'verify':
    print('WAITING_FOR_REBOOT', flush=True)
    adb('wait-for-device', timeout=120)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if sh('getprop sys.boot_completed', timeout=8) == '1':
                break
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(3)
    else:
        raise SystemExit('Boot not confirmed')

if sh('getprop ro.product.device') != 'tank' or 'uid=0(root)' not in sh("su -c 'id'"):
    raise SystemExit('Unexpected device or root unavailable')
if sh('getprop sys.boot_completed') != '1':
    raise SystemExit('Booted Fire OS required')

if phase == 'remove':
    before = packages()
    system = packages('-s')
    baseline = {'time': datetime.datetime.now().isoformat(), 'serial': SERIAL,
                'installed': sorted(before), 'enabled': sorted(packages('-e')),
                'disabled': sorted(packages('-d')), 'free_bytes': free_bytes(),
                'targets': TARGETS, 'system_targets': sorted(system.intersection(TARGETS))}
    if not CORE <= before:
        raise SystemExit('Expected retained component missing: ' + str(CORE - before))
    save('before.json', baseline)
    records = []
    for package, label in TARGETS.items():
        if package not in before:
            records.append({'package': package, 'label': label, 'result': 'already absent'})
            continue
        (OUT / (package + '-before.txt')).write_text(sh('dumpsys package ' + package), encoding='utf-8')
        # --user 0 removes the app from this profile without modifying the read-only ROM.
        result = sh("su -c 'pm uninstall --user 0 " + package + "'", timeout=120)
        print(label + ': ' + result, flush=True)
        records.append({'package': package, 'label': label, 'result': result,
                        'system_package': package in system})
        save('removed.json', records)
        if result.strip() != 'Success':
            raise RuntimeError('Uninstall not confirmed for ' + package)
    if packages().intersection(TARGETS):
        raise RuntimeError('Some target apps remain installed')
    if before - set(TARGETS) != packages():
        raise RuntimeError('Unexpected package change')
    save('after-removal.json', {'installed': sorted(packages()), 'free_bytes': free_bytes()})
    print('REMOVAL_CONFIRMED', flush=True)
elif phase == 'verify':
    before = json.loads((OUT / 'before.json').read_text(encoding='utf-8'))
    installed = packages()
    enabled = packages('-e')
    disabled = packages('-d')
    expected = set(before['installed']) - set(TARGETS)
    if installed != expected or not CORE <= enabled:
        raise RuntimeError('Unexpected retained package state')
    if not (set(before['disabled']) - set(TARGETS)) <= disabled:
        raise RuntimeError('Previous debloat or Home configuration changed')
    sh('input keyevent 224')
    sh('input keyevent 3')
    time.sleep(4)
    home = focus()
    if not any('com.amazon.tv.leanbacklauncher/' in line for line in home):
        raise RuntimeError('Home is not Leanback: ' + str(home))
    sh('am start -n com.amazon.tv.launcher/.ui.MainSettingsActivity')
    time.sleep(3)
    settings = focus()
    if not any('MainSettingsActivity' in line for line in settings):
        raise RuntimeError('Settings did not open')
    sh('input keyevent 3')
    time.sleep(3)
    current_free = free_bytes()
    report = {'boot_completed': True, 'root': sh("su -c 'id'"), 'home': home, 'settings': settings,
              'removed': TARGETS, 'retained_core_enabled': sorted(CORE),
              'unexpected_package_changes': [], 'previous_disabled_state_preserved': True,
              'free_bytes_before': before['free_bytes'], 'free_bytes_after': current_free,
              'free_bytes_difference': current_free - before['free_bytes'],
              'disabled_after': sorted(disabled), 'installed_after': sorted(installed)}
    save('verification.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('installed_after', 'disabled_after')}, ensure_ascii=False), flush=True)
else:
    raise SystemExit('Unknown phase')
