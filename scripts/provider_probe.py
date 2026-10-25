import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AAPT = os.environ.get("AAPT", "aapt")
APKS = Path(os.environ.get("APKS", ROOT / "apks"))

ELEM = re.compile(r"^(\s*)E: ([\w.-]+)(?: \(line=\d+\))?\s*$")
ATTR = re.compile(r"^\s*A: (?:http://schemas\.android\.com/apk/res/android:)?([\w:]+)\(0x[0-9a-f]+\)=(.*)$")


def clean(raw: str) -> str:
    m = re.match(r'^"([^"]*)"', raw.strip())
    return m.group(1) if m else raw.strip()


for apk in sorted(APKS.glob("*.apk")):
    r = subprocess.run([AAPT, "dump", "xmltree", str(apk), "AndroidManifest.xml"],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        continue
    stack = []
    providers = []
    for line in r.stdout.splitlines():
        em = ELEM.match(line)
        if em:
            indent = len(em.group(1))
            node = {"name": em.group(2), "attrs": {}}
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, node))
            if em.group(2) == "provider":
                providers.append(node)
            continue
        am = ATTR.match(line)
        if am and stack:
            key = am.group(1).split(":")[-1]
            stack[-1][1]["attrs"][key] = clean(am.group(2))
    if not providers:
        continue
    print(f"=== {apk.name}")
    for p in providers:
        a = p["attrs"]
        print(f"  name        : {a.get('name')}")
        print(f"  authorities : {a.get('authorities')}")
        print(f"  exported    : {a.get('exported', '(absent)')}")
        print(f"  readPerm    : {a.get('readPermission', '-')}")
        print(f"  writePerm   : {a.get('writePermission', '-')}")
        print(f"  grantUri    : {a.get('grantUriPermissions', '-')}")
        print()
