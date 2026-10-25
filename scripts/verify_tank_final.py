"""Verify root, preserved applications and debloat after a real Fire OS reboot."""
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
run_dir = root / 'analysis/amonet-live-20261025-154149'
serial = 'G070L81694972B80'
def adb(command, timeout=20):
    for attempt in range(4):
        result = subprocess.run(['adb','-s',serial,'shell',command], capture_output=True, timeout=timeout)
        output = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
        if not result.returncode:
            return output
        transport_error = any(text in output.lower() for text in ('not found','offline','closed','protocol fault','no devices'))
        if not transport_error or attempt == 3:
            raise RuntimeError(output)
        print(f'RECONNECTING_USB_FOR_READ_CHECK attempt={attempt + 1}', flush=True)
        time.sleep(attempt + 1)
        subprocess.run(['adb','-s',serial,'wait-for-device'], capture_output=True, timeout=25, check=True)

print('WAITING_FOR_FINAL_REBOOT', flush=True)
deadline = time.monotonic() + 240
while time.monotonic() < deadline:
    try:
        if adb('getprop sys.boot_completed') == '1':
            break
    except (RuntimeError, subprocess.TimeoutExpired):
        pass
    time.sleep(2)
else:
    raise SystemExit('Final Fire OS boot was not confirmed')
identity = adb("su -c 'id'")
if 'uid=0(root)' not in identity:
    raise SystemExit('Persistent root check failed')
disabled = {line.removeprefix('package:').strip() for line in adb('pm list packages -d').splitlines() if line.startswith('package:')}
enabled = {line.removeprefix('package:').strip() for line in adb('pm list packages -e').splitlines() if line.startswith('package:')}
installed = {line.removeprefix('package:').strip() for line in adb('pm list packages').splitlines() if line.startswith('package:')}
changed = set(json.loads((run_dir / 'debloat-result.json').read_text(encoding='utf-8'))['changed'])
original = set((run_dir / 'user-packages-before-root.txt').read_text(encoding='utf-8').splitlines())
core = {'com.amazon.tv.launcher','com.amazon.avod','com.amazon.venezia',
        'com.amazon.tv.settings.core','com.amazon.tv.settings.v2','com.amazon.vizzini'}
if not changed <= disabled or not original <= installed or not core <= enabled:
    raise SystemExit('Final package state checks failed')
home = adb('am start -W -a android.intent.action.MAIN -c android.intent.category.HOME', timeout=30)
if 'Error:' in home or 'Exception' in home:
    raise SystemExit('Home activity launch failed: ' + home)
activity = adb('dumpsys activity activities')
resumed = [line.strip() for line in activity.splitlines() if 'mResumedActivity' in line]
report = {'boot_completed': True, 'root_identity': identity,
          'magisk_version': adb("su -c 'magisk -v'"),
          'model': adb('getprop ro.product.model'),
          'android_version': adb('getprop ro.build.version.release'),
          'fire_os_build': adb('getprop ro.build.version.incremental'),
          'disabled_packages_persisted': sorted(changed),
          'original_packages_present': len(original), 'missing_original_packages': [],
          'protected_core_enabled': sorted(core), 'home_launch': home,
          'resumed_activity': resumed}
report['uptime_seconds'] = float(adb('cat /proc/uptime').split()[0])
(run_dir / 'final-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report), flush=True)
