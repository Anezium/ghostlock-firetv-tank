#!/usr/bin/env python3
"""Locate a `struct miscdevice` and its `fops` field in a tank kernel image.

    python scripts/find_misc_fops.py ashmem
    python scripts/find_misc_fops.py trapz

The kernel is a single `.kernel` PT_LOAD at 0xc0008000 with no KASLR, so a
miscdevice is found by scanning .data for:

    +0  int minor               (0 or 255 = MISC_DYNAMIC_MINOR)
    +4  const char *name        (pointer to a NUL-terminated string, .rodata)
    +8  const struct file_operations *fops  (pointer into .rodata)

This is how `ashmem_misc.fops = 0xc0a137b4` was found: the exploit overwrites
that one pointer with a fake table, and `misc_open()` calls `fake->open`.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KERNEL = REPO / "firmware" / "kernel-688805020.elf"

BASE = 0xC0008000
FILE_OFF = 0x124          # offset of .kernel contents in the ELF
SIZE = 0xA5DDB8           # .kernel size
DATA_START = 0xC097F000   # __end_rodata
DATA_END = 0xC0A65DB8     # __bss_start

RODATA_START = 0xC0714000
RODATA_END = 0xC097F000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="misc device name, e.g. ashmem")
    ap.add_argument("--kernel", type=Path, default=KERNEL)
    args = ap.parse_args(argv)

    blob = args.kernel.read_bytes()

    def read(addr: int, n: int) -> bytes:
        off = FILE_OFF + (addr - BASE)
        if off < 0 or off + n > len(blob):
            raise ValueError(f"address {addr:#x} outside .kernel")
        return blob[off:off + n]

    def u32(addr: int) -> int:
        return struct.unpack("<I", read(addr, 4))[0]

    def cstr(addr: int, limit: int = 64) -> str | None:
        raw = read(addr, limit)
        end = raw.find(b"\x00")
        if end <= 0:
            return None
        raw = raw[:end]
        if any(c < 0x20 or c > 0x7E for c in raw):
            return None
        return raw.decode()

    needle = args.name.encode() + b"\x00"
    data = blob[FILE_OFF:FILE_OFF + SIZE]
    hits: list[tuple[int, int, int]] = []
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        str_addr = BASE + pos
        ref = struct.pack("<I", str_addr)
        q = 0
        while True:
            q = data.find(ref, q)
            if q < 0:
                break
            name_field = BASE + q
            q += 4
            struct_addr = name_field - 4
            if not (DATA_START <= struct_addr < DATA_END):
                continue
            minor = struct.unpack("<i", read(struct_addr, 4))[0]
            fops = u32(struct_addr + 8)
            if minor not in (0, 255):
                continue
            hits.append((struct_addr, minor, fops))
        pos += 1

    if not hits:
        print("no miscdevice found for name %r" % args.name, file=sys.stderr)
        return 1

    for struct_addr, minor, fops in hits:
        kind = "dynamic" if minor == 255 else "static"
        ok = RODATA_START <= fops < RODATA_END
        print(
            f"{args.name:14s} misc={struct_addr:#010x} minor={minor:<3d} ({kind})"
            f" fops={fops:#010x} {'(.rodata)' if ok else '(?)'}"
        )
        print(f"               fops field to overwrite: {struct_addr + 8:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
