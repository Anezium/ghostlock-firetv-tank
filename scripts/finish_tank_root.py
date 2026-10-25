"""Wait for Fire OS, install its Magisk manager, and collect a debloat inventory."""
import json
from pathlib import Path
import subprocess
import time

from tank_serial import resolve_serial

root = Path(__file__).resolve().parents[1]
run_dir = root / 'analysis/amonet-live-20261025-154149'
serial = resolve_serial()
def adb(*args, timeout=20):
    result = subprocess.run(['adb','-s',serial,*args], capture_output=True, timeout=timeout)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
    if result.returncode:
        raise RuntimeError(output)
    return output

print('WAITING_FOR_FIRE_OS_BOOT_COMPLETION', flush=True)
deadline = time.monotonic() + 240
while time.monotonic() < deadline:
    if adb('shell','getprop','sys.boot_completed') == '1':
        break
    time.sleep(3)
else:
    raise SystemExit('Fire OS has not reported boot completion; inspect before continuing')
print('FIRE_OS_BOOT_COMPLETED', flush=True)
root_identity = adb('shell','su -c id')
if 'uid=0(root)' not in root_identity:
    raise SystemExit(f'Root verification failed: {root_identity}')
print(root_identity, flush=True)
output = adb('install','-r',str(root / 'amonet/magisk/Magisk-v23.0.apk'),timeout=120)
print(output, flush=True)
if 'Success' not in output:
    raise SystemExit('Magisk manager app installation was not confirmed')
packages = adb('shell','pm list packages')
(run_dir / 'packages-after-root.txt').write_text(packages + '\n', encoding='utf-8')
names = {line.removeprefix('package:').strip() for line in packages.splitlines() if line.startswith('package:')}
before = set((run_dir / 'user-packages-before-root.txt').read_text(encoding='utf-8').splitlines())
missing = sorted(before - names)
report = {'root_identity': root_identity, 'boot_completed': True,
          'original_user_packages': len(before), 'missing_user_packages': missing,
          'magisk_manager_installed': 'com.topjohnwu.magisk' in names}
(run_dir / 'root-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report), flush=True)
if missing:
    raise SystemExit('Some original packages are missing; inspect before debloat')
amazon = sorted(name for name in names if name.startswith('com.amazon.'))
print('AMAZON_PACKAGES=' + json.dumps(amazon), flush=True)
