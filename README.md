# GhostLock — one-shot root for the Fire TV Stick 2 (tank)

Build-guarded, re-playable, **one-shot** root for a stock Amazon Fire TV Stick
2nd gen (AFTT, codename `tank`) running Fire OS 5.2.9.5 build
`288.6.8.8_user_688805020` (kernel `3.10.54+`, ARM32, MT8127).

No recovery, no unlocked bootloader, no Magisk, no persistent modification: the
tool obtains a root shell for one command, and that is it. The exploit itself
only touches kernel memory; the PC side never writes outside
`/data/local/tmp`.

> **Research / authorized devices only.** The build guard is not decorative:
> the exploit uses fixed kernel addresses. Running it on another build means
> memory corruption. Read [Safety](#safety) first.

> **TL;DR — if you can open the stick, use amonet instead.** It is simpler and
> gives a real, persistent root. GhostLock only makes sense if you refuse to
> open the device. See [Should you use this?](#should-you-use-this-probably-not).

## Should you use this? Probably not

Let's be blunt: **if you are willing to open the Fire TV Stick, use amonet
instead.** The bootrom route (see `docs/GUIDE-AMONET-tank.md` and
`scripts/amonet_*`) gives you a real, persistent root — TWRP, Magisk, a normal
`su`, modules — and it survives reboots. It is also **simpler and more
reliable** overall than this exploit: no build-specific kernel offsets, no
one-shot session, no ~2 % chance of a panic per attempt.

This project exists for one narrow case: you **refuse to open the device** (no
case prying, no test point, no USB bootrom timing) and you only need one
privileged session over ADB — debloat, disable OTA, back up app data — on a
stick that is still on `288.6.8.8_user_688805020`.

If that is you, keep reading. Otherwise close this page and go flash amonet.

## Compatibility

| | |
|---|---|
| Device | Fire TV Stick 2nd gen — AFTT / `tank` |
| Build | `288.6.8.8_user_688805020` **only** |
| Kernel | `3.10.54+` (2024-03-13), ARM32, MT8127, no KASLR |
| Runs as | `shell` (uid 2000), like a stock device |
| Guard | refuses any other device / build / kernel |

An OTA removes the bug. If you want to keep the device exploitable, disable the
OTA packages first (`scripts/debloat_tank.py`).

## Quick start

Requirements: `adb`, USB debugging enabled on the stick, Python 3.9+.

```
adb devices
python scripts/gl_bench.py --serial <serial> doctor
python scripts/gl_root.py  --serial <serial> --cmd "id; getenforce"
```

Example output:

```
build:  288.6.8.8_user_688805020 (tank)
kernel: Linux version 3.10.54+ ...
attempt 1/3 ... ROOT (0.6s)
---- command output ----
uid=0(root) gid=0(root) ... context=u:r:kernel:s0

Permissive
------------------------
```

`--cmd` is one shell command line (chain with `;`). It runs in a root child of
the exploit process, its output is captured, and nothing stays behind.

## What it is good for

A one-shot maintenance shell on a stock device — the actions the `shell` user
cannot do:

- read/write other apps' private data (`/data/data/...`): backups, prefs
  patches, SQLite edits;
- `iptables` / netfilter (block OTA or telemetry at the network level);
- protected settings (`settings put secure/global`), restricted
  `dumpsys` / `am` / `pm` operations;
- persistent effects that live in `/data`: `pm disable-user`,
  `pm uninstall --user 0`, custom launcher, user APKs.

It is **not**: a permanent root, a `su`/Magisk replacement, a custom ROM, or a
way to modify `/system` (read-only, dm-verity, locked bootloader).

Note that many debloat actions (`pm disable-user`, `pm uninstall --user 0`)
already work over plain ADB. GhostLock adds the privileged layer on top.

## How it works (short version)

1. Three threads drive a PI-futex requeue race
   (`FUTEX_WAIT_REQUEUE_PI` / `FUTEX_CMP_REQUEUE_PI`). The `-EDEADLK` rollback
   removes A's `rt_mutex_waiter` from the target lock but leaves
   `A->pi_blocked_on` pointing at it.
2. A plants a fake `rt_mutex` / `plist` node over that stale waiter with
   `ioctl(ASHMEM_SET_NAME)`: the 256-byte `set_name()` stack buffer covers the
   waiter, and A then spins in userspace without any further syscall.
3. B takes the futex; the PI chain walk follows the fake node and
   `plist_del()` performs a controlled 4-byte write.
4. The write redirects one pointer — `ashmem_misc.fops` — to a fake
   `file_operations` table in our own page. B opens `/dev/ashmem`, and
   `misc_open()` calls `fake->open`.
5. The payload restores the pointer, neutralizes the fake fd
   (`file->f_op = def_chr_fops`), installs a fresh cred for the calling task
   (`uid 0`, full caps, kernel SID) and sets `selinux_enforcing = 0`.

Offsets, measurements and dead ends:
[`docs/PLAN-GHOSTLOCK-TANK.md`](docs/PLAN-GHOSTLOCK-TANK.md).

## Reliability

Per attempt: ~90–95 % on a warm system, ~80 % right after boot, ~2 % panic
(`panic_on_oops=1` → plain reboot, the exploit writes nothing to the eMMC).
`gl_root.py` retries up to `--attempts` (default 3), reboots cleanly between
attempts, and waits for the device to come back after a panic.

Measured on the reference unit:

| Campaign | Result |
|---|---|
| 40 in-process rounds | 40/40 first attempt |
| 27 CLI invocations, warm device | 27/27 first attempt |
| **20 cold boots**, full tool, ≤ 3 attempts | **20/20** (4 needed one retry) |

## Repository layout

```
probes/         trigger, stack/canary probes, final exploit (gl_exploit.c), mutex probe
scripts/        PC tooling: gl_bench.py (bench + crash black box), gl_root.py
                (one-shot root CLI), find_misc_fops.py, debloat/backup helpers
docs/           plan, offsets, measurements, guides
source-subset/  the few GPL kernel sources that matter (rtmutex.c, futex.c,
                tank_defconfig)
```

Not in the repository: the vendor kernel image, the full vendor source tree and
run logs (see `.gitignore`). Fetch them locally with `scripts/fetch_boot.py`
and `scripts/fetch_sources.py`.

## Safety

- The exploit never writes to the eMMC. A failure is a kernel panic → reboot.
- The build guard is mandatory: fixed addresses, wrong build = corruption.
- Use it only on devices you own, where this is legal.
- After a successful run SELinux stays permissive until the next reboot.
- A reboot after use is the clean thing: a failed attempt leaves stale
  PI-futex state behind, which is why the tool reboots before retrying.

## Credits

GhostLock (CVE-2026-43499) — port, tooling and measurements for `tank`.

## License

Our code (`probes/`, `scripts/`, `docs/`) is MIT — see [LICENSE](LICENSE).
`source-subset/` is Linux kernel source and remains GPL-2.0.
