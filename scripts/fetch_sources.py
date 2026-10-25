import argparse
import hashlib
import json
import re
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = 'https://fireos-tv-src.s3.amazonaws.com/BCOWueNFh33QaDsjOgPbCKELwz/index.html'


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'FireTV-ReadOnly-Audit'}), timeout=45)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan', action='store_true')
    args = parser.parse_args()
    with request(INDEX) as response:
        html = response.read().decode('utf-8')
    (ROOT / 'amazon-source-index.html').write_text(html, encoding='utf-8')
    links = re.findall(r'href=[\"\x27]([^\"\x27]+)', html)
    link = next(x for x in links if 'FireTVStick2-5.2.9.5-20230323.tar.bz2' in x)
    url = urllib.parse.urljoin(INDEX, link)
    (ROOT / 'source-url.txt').write_text(url, encoding='utf-8')
    print('SOURCE', url, flush=True)
    if not args.scan:
        return
    started = time.monotonic()
    selected = []
    members = []
    with request(url) as response, tarfile.open(fileobj=response, mode='r|bz2') as archive:
        for i, member in enumerate(archive):
            members.append({'name': member.name, 'size': member.size})
            if i < 60 or 'kernel' in member.name.lower() and member.isfile() and member.size > 10_000_000:
                print('MEMBER', member.name, member.size, flush=True)
            if member.isfile() and (member.name in ('README.txt', 'fireos.tar', 'platform.tar') or member.name.endswith(('/kernel/rtmutex.c', '/kernel/futex.c', '/mm/memory.c', '/mm/gup.c')) or ('kernel' in member.name.lower() and member.name.endswith(('.tar.gz', '.tar.bz2', '.tgz', '.zip', '.tar.xz')))):
                target = ROOT / 'amazon-sources' / Path(member.name).name
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                digest = hashlib.sha256()
                with target.open('wb') as out:
                    while chunk := source.read(1024 * 1024):
                        out.write(chunk)
                        digest.update(chunk)
                selected.append({'member': member.name, 'file': str(target), 'sha256': digest.hexdigest()})
                print('SAVED', selected[-1], flush=True)
            if time.monotonic() - started > 360:
                print('Bounded scan reached six minutes', flush=True)
                break
    (ROOT / 'source-manifest.json').write_text(json.dumps(selected, indent=2), encoding='utf-8')
    (ROOT / 'archive-members.json').write_text(json.dumps(members, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
