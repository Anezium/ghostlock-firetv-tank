import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'scripts'))

from tank_serial import adb_binary, resolve_serial

ADB = adb_binary()
DEVICE = resolve_serial()


def adb(*args):
    result = subprocess.run([ADB, '-s', DEVICE, *args], capture_output=True, timeout=35)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace').replace('\r', '')
    if result.returncode:
        raise RuntimeError(f'ADB failed: {args}: {output}')
    return output


commands = {
    'identity': 'id; cat /proc/version; getprop ro.build.version.name; getprop ro.build.fingerprint; getprop ro.build.version.security_patch; getenforce',
    'interfaces': 'ls -l /dev/ion /dev/mali /dev/ashmem /dev/binder; cat /proc/sys/kernel/perf_event_paranoid',
}
evidence = {name: adb('shell', cmd) for name, cmd in commands.items()}
remote = '/data/local/tmp/firetv-safe-probe-' + uuid.uuid4().hex[:12]
try:
    evidence['push'] = adb('push', str(ROOT / 'safe_probe'), remote)
    adb('shell', 'chmod', '700', remote)
    evidence['safe_probe'] = adb('shell', remote)
    print(evidence['safe_probe'])
finally:
    evidence['binary_cleanup'] = adb('shell', 'rm', remote)
    (ROOT / 'device-checks.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
