#!/usr/bin/env python3
"""GhostLock tank bench.

PC-side driver for a one-shot, re-playable root attempt on a stock
Fire TV Stick 2 (AFTT / tank), plus the crash black box that makes every
failed attempt produce usable forensics.

Design goals
------------
* The payload always runs as the *unprivileged* `shell` user (uid 2000) by
  default, exactly like a stock device. `--root` exists only for lab helpers
  and must never be used for the exploit itself.
* Every run is guarded by an exact build check. A wrong build means stop.
* Every run leaves a directory under analysis/gl-runs/ with the console
  output, the device-side rc, and (after a reboot) the previous boot's
  /proc/last_kmsg, parsed for the oops signature.

Typical use
-----------
    python scripts/gl_bench.py doctor
    python scripts/gl_bench.py install
    python scripts/gl_bench.py snapshot --label baseline
    python scripts/gl_bench.py run --payload probes/probe_futex_pi
    python scripts/gl_bench.py runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = REPO / "scripts" / "gl"
OUT = REPO / "analysis" / "gl-runs"

DEV = "/data/local/tmp/gl"
BIN = f"{DEV}/bin"
RUNS = f"{DEV}/runs"

EXPECTED_INCREMENTAL = "288.6.8.8_user_688805020"
EXPECTED_DEVICE = "tank"
EXPECTED_KERNEL = "3.10.54"

ADB = os.environ.get("ADB", "adb")


class BenchError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise BenchError(f"command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        raise BenchError(
            f"timeout after {timeout:.0f}s: {' '.join(cmd)}\n{out}{err}"
        ) from exc


def adb(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return _run([ADB, *args], timeout=timeout)


def pick_serial(explicit: str | None) -> str:
    p = adb("devices")
    if p.returncode != 0:
        raise BenchError(f"adb devices failed:\n{p.stderr or p.stdout}")
    devices = []
    for line in p.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        if state.strip() == "device":
            devices.append(serial)

    if explicit:
        if explicit not in devices:
            raise BenchError(
                f"device {explicit!r} not in 'adb devices' ({', '.join(devices) or 'none'})"
            )
        return explicit
    if not devices:
        raise BenchError("no adb device online")
    if len(devices) == 1:
        return devices[0]
    # The same stick can be visible twice (USB serial + Wi-Fi serial).
    non_ip = [d for d in devices if ":" not in d]
    if len(non_ip) == 1:
        return non_ip[0]
    raise BenchError(
        "several devices online; pass --serial. candidates: " + ", ".join(devices)
    )


class Device:
    def __init__(self, serial: str) -> None:
        self.serial = serial

    def shell(self, cmd: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
        return adb("-s", self.serial, "shell", cmd, timeout=timeout)

    def su(self, cmd: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
        return self.shell(f"su -c {shlex.quote(cmd)}", timeout=timeout)

    def push(self, local: Path | str, remote: str, timeout: float = 120.0) -> None:
        p = adb("-s", self.serial, "push", str(local), remote, timeout=timeout)
        if p.returncode != 0:
            raise BenchError(f"push failed: {local} -> {remote}\n{p.stderr or p.stdout}")

    def pull(self, remote: str, local: Path, timeout: float = 180.0) -> bool:
        local.parent.mkdir(parents=True, exist_ok=True)
        p = adb("-s", self.serial, "pull", remote, str(local), timeout=timeout)
        return p.returncode == 0

    def props(self) -> dict[str, str]:
        p = self.shell("getprop")
        out: dict[str, str] = {}
        for line in p.stdout.splitlines():
            m = re.match(r"^\[([^\]]+)\]: \[(.*)\]$", line.strip())
            if m:
                out[m.group(1)] = m.group(2)
        return out

    def booted(self, timeout: float = 180.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                p = self.shell("getprop sys.boot_completed", timeout=10)
            except BenchError:
                p = None
            if p is not None and p.returncode == 0 and p.stdout.strip() == "1":
                return True
            time.sleep(2)
        return False


def build_report(dev: Device) -> tuple[dict[str, str], dict[str, bool]]:
    props = dev.props()
    version = dev.shell("cat /proc/version").stdout
    values = {
        "serial": dev.serial,
        "fingerprint": props.get("ro.build.fingerprint", ""),
        "incremental": props.get("ro.build.version.incremental", ""),
        "device": props.get("ro.product.device", ""),
        "kernel": version.strip(),
        "selinux": dev.shell("getenforce").stdout.strip(),
        "panic_on_oops": dev.shell("cat /proc/sys/kernel/panic_on_oops").stdout.strip(),
        "kptr_restrict": dev.su("cat /proc/sys/kernel/kptr_restrict").stdout.strip()
        or "denied",
    }
    checks = {
        "incremental": values["incremental"] == EXPECTED_INCREMENTAL,
        "device": values["device"] == EXPECTED_DEVICE,
        "kernel": EXPECTED_KERNEL in values["kernel"],
    }
    id_out = dev.su("id").stdout.strip()
    values["root"] = id_out
    checks["root"] = "uid=0" in id_out
    return values, checks


def require_build(dev: Device) -> dict[str, str]:
    values, checks = build_report(dev)
    bad = [k for k, ok in checks.items() if not ok and k != "root"]
    if bad:
        raise BenchError(
            "build guard failed: " + ", ".join(bad) + "\n" + json.dumps(values, indent=2)
        )
    return values


def ensure_dirs(dev: Device) -> None:
    # The work dir must be owned by `shell` so that the payload (uid 2000) can
    # write its rc/pid files, and so that SELinux lets adb push into it. On the
    # lab device an earlier root-owned copy may exist: remove it via su, then
    # recreate as shell. Root can still write into a shell_data_file dir.
    probe = dev.shell(f"touch {BIN}/.wtest && rm -f {BIN}/.wtest")
    if probe.returncode != 0:
        dev.su(f"rm -rf {DEV}")
    p = dev.shell(f"mkdir -p {BIN} {RUNS} && chmod 777 {DEV} {BIN} {RUNS}")
    if p.returncode != 0:
        raise BenchError(f"cannot prepare {DEV}: {p.stderr or p.stdout}")


def install_scripts(dev: Device) -> None:
    ensure_dirs(dev)
    for name in ("blackbox.sh", "late.sh", "install.sh", "doctor.sh"):
        src = DEV_SCRIPTS / name
        if not src.exists():
            raise BenchError(f"missing local script: {src}")
        dev.push(src, f"{BIN}/{name}")
        dev.shell(f"chmod 755 {BIN}/{name}")
    p = dev.su(f"sh {BIN}/install.sh")
    print(p.stdout.strip())
    if p.returncode != 0 or "INSTALL_OK" not in p.stdout:
        raise BenchError("black box install failed")


def cmd_doctor(dev: Device, args: argparse.Namespace) -> int:
    values, checks = build_report(dev)

    print(f"serial        : {values['serial']}")
    print(f"device        : {values['device']}")
    print(f"fingerprint   : {values['fingerprint']}")
    print(f"incremental   : {values['incremental']}")
    print(f"kernel        : {values['kernel']}")
    print(f"selinux       : {values['selinux']}")
    print(f"panic_on_oops : {values['panic_on_oops']}")
    print(f"kptr_restrict : {values['kptr_restrict']}")
    print(f"root          : {values['root']}")

    hook_pfd = dev.su(
        "test -f /data/adb/post-fs-data.d/99-gl-blackbox.sh && echo yes || echo no"
    ).stdout.strip()
    hook_sd = dev.su(
        "test -f /data/adb/service.d/99-gl-late.sh && echo yes || echo no"
    ).stdout.strip()
    print(f"hook post-fs-data: {hook_pfd}")
    print(f"hook service.d   : {hook_sd}")

    p = dev.su(f"sh {BIN}/doctor.sh") if (DEV_SCRIPTS / "doctor.sh") else None
    if p is not None and p.returncode == 0:
        for line in p.stdout.splitlines():
            if line.startswith(("last_kmsg", "boot_seq", "current_boot", "pending", "ion", "mali")):
                print(f"device        : {line}")

    print("\nchecks:")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(checks[k] for k in ("incremental", "device", "kernel")):
        print("\nThis is not the expected tank build. Refusing to run anything.")
        return 3
    if not checks["root"]:
        print("\nNo root: the black box cannot be installed (lab access is optional).")
    return 0


def cmd_install(dev: Device, args: argparse.Namespace) -> int:
    require_build(dev)
    install_scripts(dev)
    print("installed. the hook now copies /proc/last_kmsg once per boot.")
    return 0


def cmd_snapshot(dev: Device, args: argparse.Namespace) -> int:
    require_build(dev)
    ensure_dirs(dev)
    p = dev.su(f"sh {BIN}/blackbox.sh manual")
    if p.returncode != 0:
        raise BenchError(f"snapshot failed:\n{p.stdout}\n{p.stderr}")

    cur = dev.shell(f"cat {DEV}/current_boot").stdout.strip()
    if not cur:
        raise BenchError("snapshot did not record current_boot")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.label or "manual")
    local = OUT / f"snap-{stamp}-{label}"
    if not dev.pull(cur, local):
        raise BenchError(f"could not pull {cur}")
    print(f"snapshot -> {local}")
    return 0


def parse_kmsg(text: str) -> dict:
    patterns = [
        ("fault_addr", r"Unable to handle kernel (?:paging request|NULL pointer dereference) at virtual address ([0-9a-fA-F]+)"),
        ("fault_addr", r"Unhandled fault: .* at 0x([0-9a-fA-F]+)"),
        ("oops_code", r"Internal error: Oops: ([0-9a-fA-F]+)"),
        ("pc", r"PC is at ([0-9a-fA-F]+)"),
        ("lr", r"LR is at ([0-9a-fA-F]+)"),
        ("pc_reg", r"pc : \[<([0-9a-fA-F]+)>\]"),
        ("lr_reg", r"lr : \[<([0-9a-fA-F]+)>\]"),
        ("panic", r"Kernel panic - not syncing: (.*)"),
        ("bug", r"(BUG:.*)"),
    ]
    sig: dict[str, str] = {}
    for key, pat in patterns:
        m = re.search(pat, text)
        if m:
            sig[key] = m.group(1).strip()
    markers = [
        m
        for m in (
            "Unable to handle kernel",
            "Internal error: Oops",
            "Kernel panic",
            "BUG:",
            "WARNING:",
            "Oops",
        )
        if m in text
    ]
    return {
        "signature": sig,
        "markers": markers,
        "clean_shutdown": "Restarting system" in text,
    }


def crash_excerpt(text: str, radius: int = 45) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Unable to handle kernel" in line or "Internal error: Oops" in line:
            lo = max(0, i - 5)
            hi = min(len(lines), i + radius)
            return "\n".join(lines[lo:hi])
    return ""


def collect_run(
    dev: Device,
    run_id: str,
    console: str,
    timed_out: bool,
    rebooted: bool,
    started: str,
) -> Path:
    local = OUT / run_id
    local.mkdir(parents=True, exist_ok=True)
    (local / "console.txt").write_text(console, encoding="utf-8", errors="replace")

    dev.pull(f"{RUNS}/{run_id}", local / "run")

    rc_path = local / "run" / "rc.txt"
    rc = rc_path.read_text(encoding="utf-8", errors="replace").strip() if rc_path.exists() else None

    boot = None
    kmsg = ""
    parsed: dict = {"signature": {}, "markers": [], "clean_shutdown": False}
    pending_match = False

    # /proc/last_kmsg is the PREVIOUS boot log. It only belongs to this run if
    # the device actually rebooted and the boot hook found our pending marker.
    # Search every boot dir with a pending.json: a bootloop can move
    # current_boot past the boot that actually consumed our marker.
    if rebooted:
        p = dev.shell(
            f'for d in {RUNS}/boot-*; do [ -f "$d/pending.json" ] && echo "$d"; done'
        )
        candidates = [line.strip() for line in p.stdout.splitlines() if line.strip()]
        for idx, cand in enumerate(candidates):
            sub = local / (f"boot-{idx}" if len(candidates) > 1 else "boot")
            if not dev.pull(cand, sub):
                continue
            pend = sub / "pending.json"
            if not pend.exists():
                continue
            try:
                match = json.loads(pend.read_text(encoding="utf-8")).get("id") == run_id
            except json.JSONDecodeError:
                match = False
            if match:
                boot = sub
                pending_match = True
                if (sub / "last_kmsg.txt").exists():
                    kmsg = (sub / "last_kmsg.txt").read_text(encoding="utf-8", errors="replace")
                    parsed = parse_kmsg(kmsg)
                    excerpt = crash_excerpt(kmsg)
                    if excerpt:
                        (local / "crash.txt").write_text(excerpt, encoding="utf-8")
                break

        # No matching pending marker: still keep the latest boot log for
        # diagnosis, but flag it as unattributed.
        if boot is None:
            cur = dev.shell(f"cat {DEV}/current_boot").stdout.strip()
            if cur:
                dev.pull(cur, local / "boot")

    # Even without a matching pending marker, an oops right after the run is
    # evidence. Parse it, but keep pending_match in the summary so the
    # attribution stays explicit.
    if not parsed["markers"]:
        log = None
        if boot and (boot / "last_kmsg.txt").exists():
            log = boot / "last_kmsg.txt"
        elif (local / "boot" / "last_kmsg.txt").exists():
            log = local / "boot" / "last_kmsg.txt"
            boot = local / "boot"
        if log is not None:
            kmsg = log.read_text(encoding="utf-8", errors="replace")
            parsed = parse_kmsg(kmsg)
            excerpt = crash_excerpt(kmsg)
            if excerpt:
                (local / "crash.txt").write_text(excerpt, encoding="utf-8")

    if rc is not None:
        status = "exit"
        dev.shell(f"rm -f {DEV}/pending")
    elif rebooted and parsed["markers"]:
        status = "crash"
    elif rebooted and pending_match:
        status = "reboot-no-oops"
    elif timed_out:
        status = "timeout"
    elif rebooted:
        status = "reboot-unrelated"
    else:
        status = "unknown"

    summary = {
        "id": run_id,
        "started": started,
        "status": status,
        "rc": rc,
        "timed_out": timed_out,
        "rebooted": rebooted,
        "pending_match": pending_match,
        "signature": parsed["signature"],
        "markers": parsed["markers"],
        "clean_shutdown": parsed["clean_shutdown"],
        "kmsg_bytes": len(kmsg),
        "boot_dir": str(boot) if boot else None,
    }
    (local / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (OUT / "index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")
    return local


def cmd_run(dev: Device, args: argparse.Namespace) -> int:
    require_build(dev)
    payload = Path(args.payload)
    if not payload.exists():
        raise BenchError(f"payload not found: {payload}")

    data = payload.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S-") + digest[:8]
    remote_payload = f"{BIN}/payload-{run_id}"
    remote_run = f"{RUNS}/{run_id}"

    ensure_dirs(dev)
    dev.push(payload, remote_payload)
    dev.shell(f"chmod 755 {remote_payload}")
    dev.shell(f"mkdir -p {remote_run}")

    argv = " ".join(shlex.quote(a) for a in args.arg)
    cmd = f"""#!/system/bin/sh
cd {DEV}
{shlex.quote(remote_payload)} {argv} &
pid=$!
echo $pid > {remote_run}/pid
wait $pid
echo $? > {remote_run}/rc.txt
"""
    local_cmd = OUT / f".cmd-{run_id}.sh"
    local_cmd.parent.mkdir(parents=True, exist_ok=True)
    local_cmd.write_text(cmd, encoding="utf-8", newline="\n")
    dev.push(local_cmd, f"{remote_run}/cmd.sh")
    dev.shell(f"chmod 755 {remote_run}/cmd.sh")
    local_cmd.unlink(missing_ok=True)

    pending = {
        "id": run_id,
        "payload": str(payload),
        "sha256": digest,
        "args": args.arg,
        "started": datetime.now().isoformat(timespec="seconds"),
        "as_root": bool(args.root),
    }
    local_pending = OUT / f".pending-{run_id}.json"
    local_pending.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    dev.push(local_pending, f"{DEV}/pending")
    # The kernel can panic microseconds after launch; make sure the marker is
    # on /data before it does, otherwise the boot hook sees nothing.
    p = dev.shell("sync")
    if p.returncode != 0:
        dev.su("sync")
    local_pending.unlink(missing_ok=True)

    started = datetime.now().isoformat(timespec="seconds")
    before_up = 0.0
    try:
        before_up = float(dev.shell("cat /proc/uptime").stdout.split()[0])
    except (ValueError, IndexError):
        pass

    print(f"run {run_id}")
    print(f"  payload: {payload} ({len(data)} bytes, sha256 {digest[:16]}...)")
    print(f"  user:    {'root (lab only)' if args.root else 'shell (uid 2000)'}")

    launch = f"sh {remote_run}/cmd.sh"
    timed_out = False
    try:
        if args.root:
            p = dev.su(launch, timeout=args.timeout)
        else:
            p = dev.shell(launch, timeout=args.timeout)
        console = (p.stdout or "") + (p.stderr or "")
    except BenchError as exc:
        timed_out = "timeout" in str(exc)
        console = str(exc) + "\n"
        # Best effort: stop an orphan payload.
        pid = dev.shell(f"cat {remote_run}/pid").stdout.strip()
        if pid.isdigit():
            dev.su(f"kill -9 {pid}")

    # A crash with panic_on_oops=1 drops adb and reboots. Wait for userspace.
    if not dev.booted(timeout=args.reboot_wait):
        print("  device did not report boot_completed; collecting anyway")

    after_up = before_up
    try:
        after_up = float(dev.shell("cat /proc/uptime").stdout.split()[0])
    except (ValueError, IndexError):
        pass
    rebooted = after_up + 1.0 < before_up

    local = collect_run(dev, run_id, console, timed_out, rebooted, started)
    summary = json.loads((local / "summary.json").read_text(encoding="utf-8"))
    print(f"  status:  {summary['status']}")
    if summary["rc"] is not None:
        print(f"  rc:      {summary['rc']}")
    if summary["signature"]:
        print("  oops:    " + ", ".join(f"{k}={v}" for k, v in summary["signature"].items()))
    elif summary["markers"]:
        print("  markers: " + ", ".join(summary["markers"]))
    print(f"  out:     {local}")
    return 0 if summary["status"] in ("exit", "crash") else 1


def cmd_runs(dev: Device | None, args: argparse.Namespace) -> int:
    if not OUT.exists():
        print("no runs yet")
        return 0
    rows = []
    for path in sorted(OUT.glob("*/summary.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    if not rows:
        print("no runs yet")
        return 0
    print(f"{'id':38} {'status':8} {'rc':>4}  signature")
    for r in rows:
        sig = ", ".join(f"{k}={v}" for k, v in r.get("signature", {}).items()) or \
              ", ".join(r.get("markers", []))
        print(f"{r['id']:38} {r['status']:8} {str(r.get('rc') or '-') :>4}  {sig}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GhostLock tank bench")
    ap.add_argument("--serial", help="adb serial (default: only online device)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="show device/build state and checks")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("install", help="install the Magisk black box hooks")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("snapshot", help="capture the current last_kmsg now")
    p.add_argument("--label", default="manual")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("run", help="run a payload as shell and collect the result")
    p.add_argument("--payload", required=True)
    p.add_argument("--arg", action="append", default=[], help="payload argument (repeatable)")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--reboot-wait", type=float, default=180.0)
    p.add_argument("--root", action="store_true", help="lab helpers only, NOT the exploit")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("runs", help="list collected runs")
    p.set_defaults(func=cmd_runs)

    args = ap.parse_args(argv)

    try:
        serial = pick_serial(args.serial)
        dev = Device(serial)
        print(f"device: {serial}\n")
        return args.func(dev, args)
    except BenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
