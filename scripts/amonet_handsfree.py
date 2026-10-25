"""Targeted USB serial transport and operator-controlled amonet-tank gates.

Stops before the first storage write until the operator creates FLASH_GO in the
new run directory. The upstream modules and their payloads are not modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'amonet/tank-convert/amonet-tank-v1.2.2/amonet'
MODULES = PACKAGE / 'modules'
sys.path.insert(0, str(MODULES))

import serial
from serial.tools import list_ports
import common
import load_payload
import main as amonet


def speak(cue):
    subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(ROOT / 'scripts/Speak-FireStickCue.ps1'), '-Cue', cue],
        check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--voice', action='store_true', help='Optional Windows speech cues')
    parser.add_argument('--require-replug', action='store_true', help='Wait for the previous USB session to disappear')
    args = parser.parse_args()
    required = ['brom-payload/build/payload.bin', 'lk-payload/build/payload.bin',
                'bin/tz.img', 'bin/lk.bin', 'bin/preloader_prod.img', 'bin/microloader.bin']
    for relative in required:
        path = PACKAGE / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Missing or empty payload: {path}')
    if args.self_check:
        print('Imports, pyserial and payload files OK; no device opened.', flush=True)
        return

    run_dir = ROOT / 'analysis' / time.strftime('amonet-live-%Y%m%d-%H%M%S')
    run_dir.mkdir(parents=True, exist_ok=False)
    print(f'RUN_DIRECTORY={run_dir}', flush=True)
    os.chdir(MODULES)

    def cue(name):
        if args.voice:
            speak(name)

    class TargetDevice(common.Device):
        def find_device(self, preloader=False):
            if preloader:
                raise RuntimeError('This runner accepts BootROM only')
            print('WAITING_FOR_BOOTROM_0E8D_0003', flush=True)
            deadline = time.monotonic() + 600
            waiting_for_unplug = args.require_replug
            while time.monotonic() < deadline:
                ports = [p for p in list_ports.comports() if p.vid == 0x0E8D]
                if waiting_for_unplug:
                    if not ports:
                        waiting_for_unplug = False
                        print('PREVIOUS_USB_SESSION_GONE_READY_FOR_REPLUG', flush=True)
                    time.sleep(0.15)
                    continue
                targets = [p for p in ports if p.pid == 0x0003]
                if len(targets) > 1:
                    raise RuntimeError('More than one MediaTek BootROM attached')
                if targets:
                    self.dev = serial.Serial(targets[0].device, common.BAUD,
                                             timeout=common.TIMEOUT, write_timeout=10)
                    print(f'BOOTROM_PORT={targets[0].device}', flush=True)
                    return
                if any(p.pid == 0x2000 for p in ports):
                    raise RuntimeError('Preloader detected; no BootROM handshake attempted')
                time.sleep(0.15)
            raise TimeoutError('No BootROM appeared within ten minutes')

        def rpmb_read(self):
            data = super().rpmb_read()
            if not hasattr(self, 'original_rpmb'):
                if data[:4] != b'AMZN':
                    raise RuntimeError('Unexpected original RPMB; stopping before storage writes')
                self.original_rpmb = data
            return data

    def removal_gate(marker):
        print('REMOVE_NEEDLE_NOW_KEEP_USB_CONNECTED', flush=True)
        cue('Remove')
        # The chat operator sends the removal instruction, then releases this
        # gate. There is no timer that can start memory access on its own.
        while not (run_dir / 'NEEDLE_REMOVED').exists():
            time.sleep(0.2)
        (run_dir / 'NEEDLE_REMOVED').unlink()
        # The operator releases this immediately after sending the chat cue;
        # leave five seconds for the physical movement before memory access.
        time.sleep(5)
        print('CHECKING_MEMORY_AFTER_NEEDLE_REMOVAL', flush=True)

    def switch_user_once(dev):
        dev.emmc_switch(0)
        block = dev.emmc_read(0)
        if len(block) != 512 or block[510:512] != b'\x55\xaa':
            raise RuntimeError('GPT signature missing; stopping')

    original_flash_data = amonet.flash_data
    write_gate_passed = False

    def guarded_flash_data(dev, data, start_block, max_size=0):
        nonlocal write_gate_passed
        if not write_gate_passed:
            print('MEMORY_CHECKS_OK_NO_STORAGE_WRITES_YET', flush=True)
            cue('Checked')
            backup_dir = run_dir / 'backup'
            backup_dir.mkdir()
            manifest = {}

            def save(name, content):
                (backup_dir / name).write_bytes(content)
                manifest[name] = {'bytes': len(content),
                                  'sha256': hashlib.sha256(content).hexdigest()}

            def read_blocks(start, count):
                result = bytearray()
                for block_index in range(start, start + count):
                    block = dev.emmc_read(block_index)
                    if len(block) != 512:
                        raise RuntimeError(f'Short backup read at sector {block_index}')
                    result.extend(block)
                return bytes(result)

            save('rpmb-original.bin', dev.original_rpmb)
            # The first amonet write targets BOOT0; restore this selection below.
            dev.emmc_switch(1)
            save('boot0-first-1MiB.bin', read_blocks(0, 2048))
            dev.emmc_switch(0)
            save('gpt-primary.bin', read_blocks(0, 34))
            gpt = amonet.parse_gpt(dev)
            (backup_dir / 'partitions.json').write_text(json.dumps(gpt, indent=2), encoding='utf-8')
            for part in ('UBOOT', 'TEE1', 'boot', 'MISC'):
                start, count = gpt[part]
                if part == 'boot':
                    count = 4
                elif part == 'MISC':
                    count = 1
                elif count > 32768:
                    raise RuntimeError(f'Unexpectedly large {part} partition')
                print(f'BACKUP {part}: {count * 512} bytes', flush=True)
                save(f'{part}-original.bin', read_blocks(start, count))
            (backup_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            dev.emmc_switch(1)
            print(f'BACKUP_COMPLETE_WAITING_FOR_OPERATOR={run_dir / "FLASH_GO"}', flush=True)
            # No timer can authorize storage writes.
            while not (run_dir / 'FLASH_GO').exists():
                time.sleep(0.2)
            (run_dir / 'FLASH_GO').unlink()
            write_gate_passed = True
            print('OPERATOR_RELEASED_STORAGE_WRITE_GATE', flush=True)
        return original_flash_data(dev, data, start_block, max_size)

    amonet.Device = TargetDevice
    amonet.switch_user = switch_user_once
    amonet.flash_data = guarded_flash_data
    load_payload.wait_for_go = removal_gate
    try:
        amonet.main()
    except Exception:
        print('STOPPED: inspect traceback before any retry', flush=True)
        try:
            cue('Failure')
        except Exception as cue_error:
            print(f'Voice cue failed: {cue_error}', flush=True)
        raise


if __name__ == '__main__':
    main()
