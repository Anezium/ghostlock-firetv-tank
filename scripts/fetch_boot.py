"""Read only boot.img from the exact public Amazon OTA, using HTTP ranges."""
import io
import json
import struct
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://d1s31zyz7dcc2d.cloudfront.net/2024/3/14/c5752488-58a3-4fe0-9ebf-9e4c3cc7d8a8/update-kindle-full_tank-288.6.8.8_user_688805020.bin'


class RangeReader(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.position = 0
        self.transferred = 0
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
            self.size = int(response.headers['Content-Length'])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        if whence == 0: self.position = offset
        elif whence == 1: self.position += offset
        elif whence == 2: self.position = self.size + offset
        if self.position < 0: raise ValueError('negative seek')
        return self.position

    def read(self, size=-1):
        if size < 0: size = self.size - self.position
        size = min(size, self.size - self.position)
        if size <= 0: return b''
        if self.transferred + size > 64 * 1024 * 1024:
            raise ValueError('Read limit exceeded')
        request = urllib.request.Request(self.url, headers={
            'Range': f'bytes={self.position}-{self.position + size - 1}',
            'User-Agent': 'FireTV-ReadOnly-Audit',
        })
        with urllib.request.urlopen(request, timeout=40) as response:
            if response.status != 206:
                raise ValueError(f'Expected range response, got {response.status}')
            result = response.read(size)
        self.position += len(result)
        self.transferred += len(result)
        return result


reader = RangeReader(URL)
print('OTA bytes:', reader.size, flush=True)
with zipfile.ZipFile(reader) as archive:
    members = archive.namelist()
    (ROOT / 'ota-members.json').write_text(json.dumps(members, indent=2), encoding='utf-8')
    targets = [name for name in members if name.endswith('boot.img')]
    if len(targets) != 1:
        raise ValueError(f'Expected one boot image, found {targets}')
    boot = archive.read(targets[0])
(ROOT / 'boot-688805020.img').write_bytes(boot)
if boot[:8] != b'ANDROID!':
    raise ValueError(f'Unexpected boot header {boot[:16]!r}')
kernel_size = struct.unpack_from('<I', boot, 8)[0]
page_size = struct.unpack_from('<I', boot, 36)[0]
kernel = boot[page_size:page_size + kernel_size]
(ROOT / 'kernel-688805020.zimage').write_bytes(kernel)
print('Boot bytes:', len(boot), 'kernel bytes:', len(kernel), 'page size:', page_size, flush=True)
cursor = 0
while True:
    cursor = kernel.find(b'\x1f\x8b\x08', cursor)
    if cursor < 0: raise ValueError('Could not find gzip-compressed kernel')
    try:
        image = zlib.decompress(kernel[cursor:], 16 + zlib.MAX_WBITS)
        if b'Linux version 3.10.54+' in image:
            (ROOT / 'kernel-688805020.raw').write_bytes(image)
            at = image.index(b'Linux version ')
            version = image[at:image.index(b'\x00', at)].decode('ascii', errors='replace')
            print('EXACT KERNEL:', version, flush=True)
            print('HTTP bytes read:', reader.transferred, flush=True)
            break
    except zlib.error:
        pass
    cursor += 1
(ROOT / 'ota-source.json').write_text(json.dumps({'url': URL, 'version': version, 'http_bytes': reader.transferred}, indent=2), encoding='utf-8')
