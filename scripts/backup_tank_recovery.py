"""Read boot/system from TWRP directly to the PC, without touching userdata."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
destination = root / 'analysis/amonet-live-20261025-154149/recovery-backup'
destination.mkdir(exist_ok=True)
serial = 'G070L81694972B80'
parts = json.loads((destination.parent / 'backup/partitions.json').read_text(encoding='utf-8'))
base = '/dev/block/platform/mtk-msdc.0/by-name/'
identity = subprocess.run(['adb','-s',serial,'shell','getprop','ro.product.device'],
                          capture_output=True, text=True, check=True).stdout.strip()
if identity != 'tank':
    raise SystemExit(f'Unexpected recovery device: {identity}')
manifest = {}
for name in ('boot', 'system'):
    expected = parts[name][1] * 512
    output = destination / f'{name}-before-magisk.img'
    partial = output.with_suffix('.img.partial')
    print(f'BACKUP_START {name} {expected} bytes', flush=True)
    chunk_size = 4 * 1048576
    with partial.open('wb') as output_stream:
        for offset in range(0, expected, chunk_size):
            size = min(chunk_size, expected - offset)
            command = f'dd if={base}{name} bs=1048576 skip={offset // 1048576} count={size // 1048576} 2>/dev/null'
            for attempt in range(4):
                result = subprocess.run(['adb','-s',serial,'exec-out',command],
                                        capture_output=True, timeout=30)
                if result.returncode == 0 and len(result.stdout) == size:
                    output_stream.write(result.stdout)
                    break
                print(f'TRANSPORT_RETRY {name} offset={offset} received={len(result.stdout)} attempt={attempt + 1}', flush=True)
                time.sleep(attempt + 1)
                subprocess.run(['adb','-s',serial,'wait-for-recovery'], timeout=30, check=True)
            else:
                raise RuntimeError(f'Cannot read a complete backup block for {name} at {offset}')
            if (offset + size) % (64 * 1048576) == 0 or offset + size == expected:
                output_stream.flush()
                print(f'BACKUP_PROGRESS {name} {offset + size}/{expected}', flush=True)
    if partial.stat().st_size != expected:
        raise RuntimeError(f'Incomplete {name} backup: {partial.stat().st_size}/{expected}')
    with partial.open('rb') as image:
        digest = hashlib.file_digest(image, 'sha256').hexdigest()
    partial.replace(output)
    manifest[output.name] = {'bytes': expected, 'sha256': digest}
    print(f'BACKUP_SAVED {name}: {expected} bytes SHA256={digest}', flush=True)
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('RECOVERY_BACKUPS_COMPLETE', flush=True)
