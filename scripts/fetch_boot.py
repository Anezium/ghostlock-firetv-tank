"""Fetch the public tank OTA boot image with HTTP ranges and extract the kernel.

The OTA is read with HTTP range requests, so only the ZIP central directory and
the boot image are transferred (a few MB, not the whole ~600 MB file).

Outputs (default: firmware/, which is git-ignored):

    boot-688805020.img        Android boot image
    kernel-688805020.zimage   compressed kernel payload
    kernel-688805020.raw      decompressed kernel: input for vmlinux-to-elf
    ota-members.json          ZIP member list
    ota-source.json           URL, kernel version and bytes actually read

Usage:
    python scripts/fetch_boot.py [--dest firmware]

Then rebuild the analysable ELF:

    pip install vmlinux-to-elf
    vmlinux-to-elf firmware/kernel-688805020.raw firmware/kernel-688805020.elf
"""

from __future__ import annotations

import argparse
import io
import json
import lzma
import struct
import urllib.request
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
URL = (
    "https://d1s31zyz7dcc2d.cloudfront.net/2024/3/14/"
    "c5752488-58a3-4fe0-9ebf-9e4c3cc7d8a8/"
    "update-kindle-full_tank-288.6.8.8_user_688805020.bin"
)
MAX_BYTES = 64 * 1024 * 1024


class RangeReader(io.RawIOBase):
    """Minimal seekable file object over HTTP range requests."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.position = 0
        self.transferred = 0
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            self.size = int(response.headers["Content-Length"])

    def seekable(self) -> bool: return True
    def readable(self) -> bool: return True
    def tell(self) -> int: return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.position = offset
        elif whence == 1:
            self.position += offset
        elif whence == 2:
            self.position = self.size + offset
        if self.position < 0:
            raise ValueError("negative seek")
        return self.position

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size <= 0:
            return b""
        if self.transferred + size > MAX_BYTES:
            raise ValueError("read limit exceeded")
        request = urllib.request.Request(self.url, headers={
            "Range": f"bytes={self.position}-{self.position + size - 1}",
            "User-Agent": "FireTV-ReadOnly-Audit",
        })
        with urllib.request.urlopen(request, timeout=40) as response:
            if response.status != 206:
                raise ValueError(f"expected range response, got {response.status}")
            result = response.read(size)
        self.position += len(result)
        self.transferred += len(result)
        return result


def decompress_kernel(payload: bytes) -> tuple[bytes, str]:
    """Return (vmlinux, version) from the compressed payload inside the zImage.

    The payload is XZ here (CONFIG_KERNEL_XZ), but we also accept gzip, and we
    validate the result by looking for the version banner. The zImage stub
    contains the magic bytes as string constants, hence the scan-and-test.
    """
    for magic, fmt in ((b"\xfd7zXZ\x00", "xz"), (b"\x1f\x8b\x08", "gzip")):
        pos = 0
        while True:
            pos = payload.find(magic, pos)
            if pos < 0:
                break
            try:
                if fmt == "xz":
                    image = lzma.LZMADecompressor(format=lzma.FORMAT_XZ).decompress(payload[pos:])
                else:
                    image = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(payload[pos:])
            except (lzma.LZMAError, zlib.error):
                pos += 1
                continue
            at = image.find(b"Linux version ")
            if at >= 0 and b"3.10.54+" in image[at:at + 64]:
                version = image[at:image.index(b"\x00", at)].decode("ascii", "replace")
                return image, version
            pos += 1
    raise SystemExit("no XZ/gzip kernel payload found (wrong boot image?)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=REPO / "firmware",
                        help="output directory (default: firmware/)")
    args = parser.parse_args(argv)
    out = args.dest
    out.mkdir(parents=True, exist_ok=True)

    reader = RangeReader(URL)
    print(f"OTA bytes: {reader.size}", flush=True)

    with zipfile.ZipFile(reader) as archive:
        members = archive.namelist()
        (out / "ota-members.json").write_text(json.dumps(members, indent=2), encoding="utf-8")
        targets = [name for name in members if name.endswith("boot.img")]
        if len(targets) != 1:
            raise SystemExit(f"expected one boot image, found {targets}")
        boot = archive.read(targets[0])

    (out / "boot-688805020.img").write_bytes(boot)
    if boot[:8] != b"ANDROID!":
        raise SystemExit(f"unexpected boot header {boot[:16]!r}")

    kernel_size = struct.unpack_from("<I", boot, 8)[0]
    page_size = struct.unpack_from("<I", boot, 36)[0]
    kernel = boot[page_size:page_size + kernel_size]
    (out / "kernel-688805020.zimage").write_bytes(kernel)
    print(f"boot bytes: {len(boot)}, kernel bytes: {len(kernel)}, page size: {page_size}",
          flush=True)

    cursor = 0
    image, version = decompress_kernel(kernel)
    (out / "kernel-688805020.raw").write_bytes(image)
    print(f"EXACT KERNEL: {version}", flush=True)
    print(f"HTTP bytes read: {reader.transferred}", flush=True)

    (out / "ota-source.json").write_text(
        json.dumps({"url": URL, "version": version, "http_bytes": reader.transferred}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {out}/kernel-688805020.raw — now run vmlinux-to-elf", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
