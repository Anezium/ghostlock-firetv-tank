"""One read-only sector request to an already running amonet payload."""
import json
import argparse
from pathlib import Path
import struct
import time
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wait-seconds', type=int, default=0)
args = parser.parse_args()
deadline = time.monotonic() + args.wait_seconds
print('READ_ONLY_PROBE_WAITING_FOR_USB', flush=True)
while True:
    targets = [p for p in list_ports.comports() if (p.vid, p.pid) == (0x0E8D, 0x0003)]
    if targets or time.monotonic() >= deadline:
        break
    time.sleep(0.2)
if len(targets) != 1:
    raise SystemExit('No unique connected BootROM/payload port; no request sent')
with serial.Serial(targets[0].device, 115200, timeout=4, write_timeout=4) as port:
    pending = port.read(port.in_waiting)
    print(json.dumps({'port': targets[0].device, 'pending_bytes': len(pending)}), flush=True)
    # Avoid merging the three USB commands in the Windows VCOM driver.
    for word in (0xF00DD00D, 0x1000, 0):
        port.write(struct.pack('>I', word))
        port.flush()
        time.sleep(0.03)
    block = port.read(512)
    print(json.dumps({'received_bytes': len(block),
                      'mbr_signature': block[-2:].hex() if len(block) == 512 else None,
                      'pending_after_read': port.in_waiting}), flush=True)
    if len(block) == 512 and block[-2:] == b'\x55\xaa':
        output = Path(__file__).resolve().parents[1] / 'analysis/payload-readonly-mbr.bin'
        output.write_bytes(block)
        print(f'VALID_MBR_SAVED={output}', flush=True)
