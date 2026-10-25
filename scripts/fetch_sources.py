"""Download the Amazon Fire OS 5.2.9.5 source drop and extract the kernel sources.

The index page lists the GPL source tarballs published by Amazon. The tarball is
streamed (``--scan``) and only the members we care about are written: the
README, the ``fireos.tar``/``platform.tar`` archives, and the few files that
matter for the offset work (rtmutex.c, futex.c, memory.c, gup.c).

Outputs (default: amazon-sources/, git-ignored):

    amazon-source-index.html   raw index page
    source-url.txt             resolved tarball URL
    source-manifest.json       extracted members + sha256
    archive-members.json       every member seen during the scan

Usage:
    python scripts/fetch_sources.py           # index only, prints the tarball URL
    python scripts/fetch_sources.py --scan    # stream the tarball (bounded to 6 min)

Note: the full ``--scan`` is several hundred MB over HTTP. The curated subset
used by the exploit lives in ``source-subset/`` and is committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INDEX = "https://fireos-tv-src.s3.amazonaws.com/BCOWueNFh33QaDsjOgPbCKELwz/index.html"
SCAN_SECONDS = 360


def request(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "FireTV-ReadOnly-Audit"})
    return urllib.request.urlopen(req, timeout=45)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true",
                        help="also stream the tarball and extract selected members")
    parser.add_argument("--dest", type=Path, default=REPO / "amazon-sources",
                        help="output directory (default: amazon-sources/)")
    args = parser.parse_args(argv)
    out = args.dest
    out.mkdir(parents=True, exist_ok=True)

    with request(INDEX) as response:
        html = response.read().decode("utf-8")
    (out / "amazon-source-index.html").write_text(html, encoding="utf-8")

    links = re.findall(r'href=["\']([^"\']+)', html)
    try:
        link = next(x for x in links if "FireTVStick2-5.2.9.5-20230323.tar.bz2" in x)
    except StopIteration:
        raise SystemExit("the 5.2.9.5 tarball is not in the index; check the saved HTML")
    url = urllib.parse.urljoin(INDEX, link)
    (out / "source-url.txt").write_text(url, encoding="utf-8")
    print(f"SOURCE {url}", flush=True)
    if not args.scan:
        return 0

    started = time.monotonic()
    selected = []
    members = []
    with request(url) as response, tarfile.open(fileobj=response, mode="r|bz2") as archive:
        for i, member in enumerate(archive):
            members.append({"name": member.name, "size": member.size})
            if i < 60 or ("kernel" in member.name.lower() and member.isfile()
                          and member.size > 10_000_000):
                print(f"MEMBER {member.name} {member.size}", flush=True)
            wanted = (
                member.isfile()
                and (
                    member.name in ("README.txt", "fireos.tar", "platform.tar")
                    or member.name.endswith(("/kernel/rtmutex.c", "/kernel/futex.c",
                                             "/mm/memory.c", "/mm/gup.c"))
                    or ("kernel" in member.name.lower()
                        and member.name.endswith((".tar.gz", ".tar.bz2", ".tgz", ".zip", ".tar.xz")))
                )
            )
            if wanted:
                target = out / Path(member.name).name
                source = archive.extractfile(member)
                digest = hashlib.sha256()
                with target.open("wb") as handle:
                    while chunk := source.read(1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
                selected.append({"member": member.name, "file": str(target),
                                 "sha256": digest.hexdigest()})
                print(f"SAVED {selected[-1]}", flush=True)
            if time.monotonic() - started > SCAN_SECONDS:
                print(f"bounded scan reached {SCAN_SECONDS} s", flush=True)
                break

    (out / "source-manifest.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
    (out / "archive-members.json").write_text(json.dumps(members, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
