"""Wait for and inspect only this user's Fire TV fastboot serial."""
import subprocess
import time

from tank_serial import fastboot_binary, resolve_serial

serial = resolve_serial(tool='fastboot')
deadline = time.monotonic() + 180
print('WAITING_FOR_FIRE_TV_FASTBOOT', flush=True)
while time.monotonic() < deadline:
    result = subprocess.run([fastboot_binary(), 'devices'], capture_output=True, text=True, timeout=10)
    if any(line.split() and line.split()[0] == serial for line in result.stdout.splitlines()):
        print(f'FASTBOOT_SERIAL={serial}', flush=True)
        for variable in ('product', 'unlocked', 'secure'):
            result = subprocess.run([fastboot_binary(), '-s', serial, 'getvar', variable],
                                    capture_output=True, text=True, timeout=15)
            print(result.stdout + result.stderr, flush=True)
        break
    time.sleep(0.5)
else:
    raise SystemExit('No matching fastboot device appeared within three minutes')
