"""Install the verified Magisk 23 ZIP through the running tank TWRP."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
run_dir = root / 'analysis/amonet-live-20261025-154149'
backup_dir = run_dir / 'recovery-backup'
manifest = json.loads((backup_dir / 'manifest.json').read_text(encoding='utf-8'))
for name, record in manifest.items():
    path = backup_dir / name
    with path.open('rb') as image:
        digest = hashlib.file_digest(image, 'sha256').hexdigest()
    if path.stat().st_size != record['bytes'] or digest != record['sha256']:
        raise SystemExit(f'Backup verification failed: {name}')
apk = root / 'amonet/magisk/Magisk-v23.0.apk'
if hashlib.sha256(apk.read_bytes()).hexdigest() != '079bc3a7f67413cb12509d1b811958dd7e7c7fb593d3f0507954fea72077b524':
    raise SystemExit('Magisk asset hash changed')
serial = 'G070L81694972B80'
def adb(*args, timeout=60):
    result = subprocess.run(['adb','-s',serial,*args], capture_output=True, timeout=timeout)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(f'adb command failed: {args}: {output}')
    return output

if 'uid=0(root)' not in adb('shell','id') or '3.2.3' not in adb('shell','getprop','ro.twrp.version'):
    raise SystemExit('Expected rooted TWRP is not connected')
print(adb('push',str(apk),'/sdcard/Magisk-v23.0.zip'), flush=True)
output = adb('shell','twrp','install','/sdcard/Magisk-v23.0.zip',timeout=240)
(run_dir / 'magisk-install-output.txt').write_text(output, encoding='utf-8')
print(output, flush=True)
print(adb('pull','/tmp/recovery.log',str(run_dir / 'recovery-after-magisk.log')), flush=True)
adb('shell','twrp','mount','/system')
version = adb('shell','/data/adb/magisk/magisk32','-c')
print('MAGISK_BINARY_VERSION=' + version, flush=True)
if '23.0' not in version:
    raise SystemExit('Magisk 23 binary verification failed; do not reboot yet')
print('MAGISK_INSTALLED_IN_RECOVERY_NOT_YET_REBOOTED', flush=True)
