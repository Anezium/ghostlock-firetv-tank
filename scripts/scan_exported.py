import re
import subprocess
import sys
from pathlib import Path

ADB = r"C:\Users\saim2\AppData\Local\Android\Sdk\platform-tools\adb.exe"
DEV = "192.168.1.172:5555"
AAPT = r"C:\Users\saim2\AppData\Local\Android\Sdk\build-tools\30.0.3\aapt.exe"
OUT = Path(r"E:\Tools\FireStick\apks")

PKGS = [
    "com.amazon.platform.fdrw", "com.amazon.ssmsys", "com.amazon.bueller.notification",
    "amazon.fireos", "com.amazon.wcast.sink", "com.amazon.android.marketplace",
    "com.amazon.tifobserver", "com.amazon.neodelegate", "com.android.providers.settings",
    "com.android.keychain", "com.amazon.device.sale.service",
    "com.amazon.acos.providers.UnifiedSettingsProvider", "com.dolby",
    "com.android.settings", "com.amazon.tv.settings.core", "android.amazon.perm",
    "com.amazon.android.service.networkmonitor", "com.android.location.fused",
    "com.android.systemui", "com.amazon.bluetoothinternals", "com.amazon.connectivitydiag",
]

APK_OF = {
    "com.amazon.platform.fdrw": "/system/app/fdrw/fdrw.apk",
    "com.amazon.ssmsys": "/system/priv-app/SystemStatusMonitorSys/SystemStatusMonitorSys.apk",
    "com.amazon.bueller.notification": "/system/priv-app/FireTvNotificationService/FireTvNotificationService.apk",
    "amazon.fireos": "/system/framework/fireos-res/fireos-res.apk",
    "com.amazon.wcast.sink": "/system/priv-app/WhispercastConnect/WhispercastConnect.apk",
    "com.amazon.android.marketplace": "/system/priv-app/marketplace_service_receiver/marketplace_service_receiver.apk",
    "com.amazon.tifobserver": "/system/priv-app/TIFObserverService/TIFObserverService.apk",
    "com.amazon.neodelegate": "/system/priv-app/com.amazon.neo.delegateservice/com.amazon.neo.delegateservice.apk",
    "com.android.providers.settings": "/system/priv-app/SettingsProvider/SettingsProvider.apk",
    "com.android.keychain": "/system/app/KeyChain/KeyChain.apk",
    "com.amazon.device.sale.service": "/system/priv-app/FireTvSaleService/FireTvSaleService.apk",
    "com.amazon.acos.providers.UnifiedSettingsProvider": "/system/app/UnifiedSettingsProvider/UnifiedSettingsProvider.apk",
    "com.dolby": "/system/vendor/app/Ds/Ds.apk",
    "com.android.settings": "/system/priv-app/CredentialStorage/CredentialStorage.apk",
    "com.amazon.tv.settings.core": "/system/priv-app/com.amazon.tv.settings.core/com.amazon.tv.settings.core.apk",
    "android.amazon.perm": "/system/framework/android.amazon.perm/android.amazon.perm.apk",
    "com.amazon.android.service.networkmonitor": "/system/priv-app/AmazonNetworkMonitor/AmazonNetworkMonitor.apk",
    "com.android.location.fused": "/system/priv-app/FusedLocation/FusedLocation.apk",
    "com.android.systemui": "/system/priv-app/FireTVSystemUI/FireTVSystemUI.apk",
    "com.amazon.bluetoothinternals": "/system/priv-app/BluetoothInternals/BluetoothInternals.apk",
    "com.amazon.connectivitydiag": "/system/priv-app/ConnectivityDiag/ConnectivityDiag.apk",
}

ATTR = re.compile(r"^\s*A: (?:http://schemas\.android\.com/apk/res/android:)?([\w:]+)\(0x[0-9a-f]+\)=(.*)$")
ELEM = re.compile(r"^(\s*)E: ([\w.-]+)(?: \(line=\d+\))?\s*$")

COMPONENTS = {"activity", "activity-alias", "service", "receiver", "provider"}


def attr_value(raw: str):
    raw = raw.strip()
    m = re.match(r'^"(.*)"', raw)
    if m:
        return m.group(1)
    m = re.match(r"^\(type 0x[0-9a-f]+\)(0x[0-9a-f]+)", raw)
    if m:
        v = int(m.group(1), 16)
        return True if v == 0xFFFFFFFF else (False if v == 0 else v)
    return raw


def parse(apk: Path):
    r = subprocess.run([AAPT, "dump", "xmltree", str(apk), "AndroidManifest.xml"],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        return None, r.stderr[:200]
    stack = []
    comps = []
    for line in r.stdout.splitlines():
        em = ELEM.match(line)
        if em:
            indent = len(em.group(1))
            name = em.group(2)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            node = {"name": name, "attrs": {}, "parent": stack[-1][1] if stack else None,
                    "children": []}
            if stack:
                stack[-1][1]["children"].append(node)
            stack.append((indent, node))
            if name in COMPONENTS:
                comps.append(node)
            continue
        am = ATTR.match(line)
        if am and stack:
            key = am.group(1)
            key = key.split(":")[-1]
            stack[-1][1]["attrs"][key] = attr_value(am.group(2))
    return comps, None


def actions_of(node):
    acts = []
    for c in node["children"]:
        if c["name"] == "intent-filter":
            for a in c["children"]:
                if a["name"] in ("action", "data") and "name" in a["attrs"]:
                    acts.append(str(a["attrs"]["name"]))
                elif a["name"] == "data":
                    for k, v in a["attrs"].items():
                        acts.append(f"{k}={v}")
    return acts


OUT.mkdir(parents=True, exist_ok=True)
report = []
for pkg in PKGS:
    path = APK_OF[pkg]
    local = OUT / (pkg.replace(".", "_") + ".apk")
    if not local.exists():
        r = subprocess.run([ADB, "-s", DEV, "pull", path, str(local)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            report.append(f"## {pkg}: PULL FAILED {r.stderr.strip()[:120]}")
            continue
    comps, err = parse(local)
    if comps is None:
        report.append(f"## {pkg}: PARSE FAILED {err}")
        continue
    open_comps = []
    for c in comps:
        exported = c["attrs"].get("exported")
        perm = c["attrs"].get("permission")
        acts = actions_of(c)
        effective = exported is True or (exported is None and acts)
        if effective and not perm:
            open_comps.append((c["name"], c["attrs"].get("name"), acts))
    if open_comps:
        report.append(f"## {pkg} ({len(open_comps)} composant(s) ouvert(s))")
        for typ, name, acts in open_comps:
            a = ", ".join(acts[:4]) if acts else "-"
            report.append(f"   {typ:12} {name}  [{a}]")
    else:
        report.append(f"## {pkg}: rien d'ouvert")

text = "\n".join(report)
print(text)
Path(r"E:\Tools\FireStick\analysis\exported-components.txt").write_text(text, encoding="utf-8")
