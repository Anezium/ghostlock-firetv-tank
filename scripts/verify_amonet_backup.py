"""Check saved critical regions and intended amonet image bounds before flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run_directory', type=Path)
args = parser.parse_args()
backup = args.run_directory / 'backup'
manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
required = {'rpmb-original.bin', 'boot0-first-1MiB.bin', 'gpt-primary.bin',
            'UBOOT-original.bin', 'TEE1-original.bin', 'boot-original.bin', 'MISC-original.bin'}
if set(manifest) != required:
    raise SystemExit('Unexpected backup file set')
data = {}
for name in sorted(required):
    content = (backup / name).read_bytes()
    record = manifest[name]
    if len(content) != record['bytes'] or hashlib.sha256(content).hexdigest() != record['sha256']:
        raise SystemExit(f'Backup size/hash mismatch: {name}')
    data[name] = content
if len(data['rpmb-original.bin']) != 256 or not data['rpmb-original.bin'].startswith(b'AMZN'):
    raise SystemExit('Unexpected original RPMB')
if len(data['boot0-first-1MiB.bin']) != 1048576 or not data['boot0-first-1MiB.bin'].startswith(b'EMMC_BOOT'):
    raise SystemExit('Unexpected original BOOT0')
gpt = data['gpt-primary.bin']
if len(gpt) != 34 * 512 or gpt[510:512] != b'\x55\xaa' or gpt[512:520] != b'EFI PART':
    raise SystemExit('Invalid saved GPT signatures')
header_size = struct.unpack_from('<I', gpt, 512 + 12)[0]
if not 92 <= header_size <= 512:
    raise SystemExit('Invalid GPT header size')
header = bytearray(gpt[512:512 + header_size])
expected_crc = struct.unpack_from('<I', header, 16)[0]
header[16:20] = bytes(4)
if zlib.crc32(header) != expected_crc:
    raise SystemExit('Saved GPT header CRC does not match')
entries_lba, entries_count, entry_size, entries_crc = struct.unpack_from('<QIII', gpt, 512 + 72)
entries_start = entries_lba * 512
entries_end = entries_start + entries_count * entry_size
if entries_end > len(gpt) or zlib.crc32(gpt[entries_start:entries_end]) != entries_crc:
    raise SystemExit('Saved GPT partition array CRC does not match')
boot = data['boot-original.bin']
if len(boot) != 2048 or not (boot.startswith(b'ANDROID!') or boot[1024:1032] == b'ANDROID!'):
    raise SystemExit('Unrecognized original boot image header')
parts = json.loads((backup / 'partitions.json').read_text(encoding='utf-8'))
package = Path(__file__).resolve().parents[1] / 'amonet/tank-convert/amonet-tank-v1.2.2/amonet'
checks = []
for name, relative in [('UBOOT', 'bin/lk.bin'), ('TEE1', 'bin/tz.img')]:
    original_size = parts[name][1] * 512
    if len(data[f'{name}-original.bin']) != original_size:
        raise SystemExit(f'Incomplete partition backup: {name}')
    image = (package / relative).read_bytes()
    if ((len(image) + 511) // 512) * 512 > original_size:
        raise SystemExit(f'Image exceeds partition: {relative}')
    checks.append({'partition': name, 'image_bytes': len(image), 'partition_bytes': original_size})
for relative, limit in [('bin/preloader_prod.img', 0x80000),
                        ('lk-payload/build/payload.bin', 0x80000),
                        ('bin/microloader.bin', 1024)]:
    if (package / relative).stat().st_size > limit:
        raise SystemExit(f'BOOT0/boot region size exceeded: {relative}')
if len(data['MISC-original.bin']) != 512:
    raise SystemExit('Incomplete original MISC sector')
report = {'verified': True, 'files': sorted(required), 'gpt_crc_valid': True, 'image_bounds': checks}
(args.run_directory / 'backup-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
