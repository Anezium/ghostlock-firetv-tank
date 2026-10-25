"""Resolve the Fire TV Stick 2 serial for the tank helper scripts.

The lab scripts used to hardcode one device serial. They now accept:

1. an explicit argument (scripts that take one pass it here),
2. ``$TANK_SERIAL``,
3. ``$ADB_SERIAL``,
4. auto-detection: the only online adb device, or the only one whose
   ``ro.product.device`` is ``tank``.

For fastboot helpers use ``resolve_serial(tool="fastboot")``: auto-detection
then reads ``fastboot devices`` (there is only one candidate in that mode).

``ADB`` / ``FASTBOOT`` environment variables override the binary paths.
"""

from __future__ import annotations

import os
import subprocess

DEVICE = "tank"


def adb_binary() -> str:
    return os.environ.get("ADB", "adb")


def fastboot_binary() -> str:
    return os.environ.get("FASTBOOT", "fastboot")


def _run(cmd: list[str], timeout: float = 15.0):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _devices(tool: str) -> list[str]:
    binary = adb_binary() if tool == "adb" else fastboot_binary()
    p = _run([binary, "devices"])
    if p is None or p.returncode != 0:
        return []
    found = []
    for line in p.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            found.append(parts[0])
    return found


def _is_tank(serial: str) -> bool:
    p = _run([adb_binary(), "-s", serial, "shell", "getprop", "ro.product.device"])
    return bool(p and p.returncode == 0 and p.stdout.strip() == DEVICE)


def resolve_serial(explicit: str | None = None, tool: str = "adb") -> str:
    for candidate in (explicit, os.environ.get("TANK_SERIAL"), os.environ.get("ADB_SERIAL")):
        if candidate:
            return candidate

    devices = _devices(tool)
    if len(devices) == 1:
        return devices[0]

    if tool == "adb":
        tanks = [serial for serial in devices if _is_tank(serial)]
        if len(tanks) == 1:
            return tanks[0]

    raise SystemExit(
        "cannot pick the Fire TV Stick serial: pass it explicitly or set TANK_SERIAL.\n"
        f"online {tool} devices: {', '.join(devices) or 'none'}"
    )
