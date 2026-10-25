#!/usr/bin/env python3
"""Locate a `struct miscdevice` and its `fops` field in a tank kernel ELF.

    python scripts/find_misc_fops.py ashmem
    python scripts/find_misc_fops.py trapz --kernel firmware/kernel-688805020.elf

The kernel is a 32-bit little-endian ELF (fixed load address, no KASLR). A
miscdevice is found by scanning the PT_LOAD segments for:

    +0  int minor                             (0 or 255 = MISC_DYNAMIC_MINOR)
    +4  const char *name                      (pointer to the NUL-terminated name)
    +8  const struct file_operations *fops    (pointer inside a mapped segment)

Output: the struct address, the minor, the fops pointer and — what matters for
the exploit — the address of the *fops field* (struct + 8). For this build:

    ashmem  misc=0xc0a137ac  fops=0xc075fac0  field=0xc0a137b4

This is layout-independent (it parses the program headers), so it still works
after regenerating the ELF with vmlinux-to-elf.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_KERNEL = REPO / "firmware" / "kernel-688805020.elf"

PT_LOAD = 1


class Elf32:
    def __init__(self, path: Path) -> None:
        self.blob = path.read_bytes()
        if self.blob[:4] != b"\x7fELF" or self.blob[4] != 1:
            raise SystemExit(f"{path}: not a 32-bit ELF")
        phoff = self.u16(28) | (self.u16(30) << 16)
        phentsize = self.u16(42)
        phnum = self.u16(44)
        self.segments: list[tuple[int, int, int]] = []  # file offset, vaddr, filesz
        for i in range(phnum):
            base = phoff + i * phentsize
            if self.u32(base) != PT_LOAD:
                continue
            offset = self.u32(base + 4)
            vaddr = self.u32(base + 8)
            filesz = self.u32(base + 16)
            if filesz:
                self.segments.append((offset, vaddr, filesz))
        if not self.segments:
            raise SystemExit(f"{path}: no PT_LOAD segment")

    def u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.blob, offset)[0]

    def u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.blob, offset)[0]

    def read(self, addr: int, size: int) -> bytes | None:
        for offset, vaddr, filesz in self.segments:
            if vaddr <= addr and addr + size <= vaddr + filesz:
                start = offset + (addr - vaddr)
                return self.blob[start:start + size]
        return None

    def u32_at(self, addr: int) -> int | None:
        data = self.read(addr, 4)
        return struct.unpack("<I", data)[0] if data is not None else None

    def cstring(self, addr: int, limit: int = 64) -> str | None:
        data = self.read(addr, limit)
        if data is None:
            return None
        end = data.find(b"\x00")
        if end <= 0:
            return None
        data = data[:end]
        if any(byte < 0x20 or byte > 0x7E for byte in data):
            return None
        return data.decode("ascii")

    def mapped(self, addr: int, size: int = 4) -> bool:
        return self.read(addr, size) is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="misc device name, e.g. ashmem")
    parser.add_argument("--kernel", type=Path, default=DEFAULT_KERNEL,
                        help=f"kernel ELF (default: {DEFAULT_KERNEL.relative_to(REPO)})")
    args = parser.parse_args(argv)

    elf = Elf32(args.kernel)
    needle = args.name.encode() + b"\x00"

    # Every address where the literal name appears.
    string_addrs: list[int] = []
    for offset, vaddr, filesz in elf.segments:
        chunk = elf.blob[offset:offset + filesz]
        pos = 0
        while True:
            pos = chunk.find(needle, pos)
            if pos < 0:
                break
            string_addrs.append(vaddr + pos)
            pos += 1

    if not string_addrs:
        print(f"name {args.name!r} not found in the image", file=sys.stderr)
        return 1

    # Pointers to those strings, then validate the miscdevice shape.
    hits: dict[int, tuple[int, int]] = {}
    for string_addr in string_addrs:
        pointer = struct.pack("<I", string_addr)
        for offset, vaddr, filesz in elf.segments:
            chunk = elf.blob[offset:offset + filesz]
            pos = 0
            while True:
                pos = chunk.find(pointer, pos)
                if pos < 0:
                    break
                name_field = vaddr + pos
                pos += 4
                if name_field < 4:
                    continue
                struct_addr = name_field - 4
                minor = elf.u32_at(struct_addr)
                fops = elf.u32_at(struct_addr + 8)
                if minor not in (0, 255) or fops is None or not elf.mapped(fops):
                    continue
                hits[struct_addr] = (minor, fops)

    if not hits:
        print(f"no miscdevice found for {args.name!r}", file=sys.stderr)
        return 1

    for struct_addr, (minor, fops) in sorted(hits.items()):
        kind = "dynamic" if minor == 255 else "static"
        print(f"{args.name:14s} misc={struct_addr:#010x} minor={minor:<3d} ({kind}) "
              f"fops={fops:#010x}")
        print(f"{'':14s} fops field to overwrite: {struct_addr + 8:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
