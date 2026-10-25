"""Install the bundled tank TWRP using the upstream fastboot-step sequence."""
from pathlib import Path
import subprocess

from tank_serial import fastboot_binary, resolve_serial

root = Path(__file__).resolve().parents[1]
package = root / 'amonet/tank-convert/amonet-tank-v1.2.2/amonet'
serial = resolve_serial(tool='fastboot')
log_file = root / 'analysis/tank-recovery-flash.log'

def run(*arguments):
    result = subprocess.run([fastboot_binary(), '-s', serial, *map(str, arguments)],
                            capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    print(output, flush=True)
    with log_file.open('a', encoding='utf-8') as log:
        log.write('fastboot ' + ' '.join(map(str, arguments)) + '\n' + output + '\n')
    if result.returncode:
        raise RuntimeError(f'fastboot failed: {arguments}')
    return output

product = run('getvar', 'product')
if 'product: TANK' not in product:
    raise SystemExit('Unexpected fastboot product; nothing flashed')
recovery = package / 'bin/twrp.img'
with recovery.open('rb') as image:
    if image.read(8) != b'ANDROID!':
        raise SystemExit('Unexpected recovery image header')
run('flash', 'recovery', recovery)
run('flash', 'TEE2', package / 'bin/tz.img')
run('oem', 'reboot-recovery')
print('RECOVERY_FLASHED_REBOOT_REQUESTED', flush=True)
