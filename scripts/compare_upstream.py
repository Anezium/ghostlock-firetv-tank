import hashlib
import subprocess
import sys
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1]
VENDOR = AUDIT / "kernel-src"
V54 = AUDIT / "upstream" / "linux-3.10.54"
V108 = AUDIT / "upstream" / "linux-3.10.108"

FILES = [
    "kernel/futex.c", "kernel/ptrace.c", "kernel/exit.c", "kernel/fork.c",
    "kernel/sys.c", "kernel/cred.c", "kernel/signal.c", "kernel/module.c",
    "kernel/pid.c", "kernel/user.c", "kernel/groups.c", "kernel/audit.c",
    "kernel/auditsc.c", "kernel/events/core.c", "kernel/trace/trace.c",
    "kernel/time/posix-timers.c", "kernel/sched/core.c",
    "mm/memory.c", "mm/mmap.c", "mm/madvise.c", "mm/shmem.c",
    "mm/msync.c", "mm/rmap.c", "mm/swapfile.c",
    "fs/pipe.c", "fs/proc/base.c", "fs/proc/task_mmu.c", "fs/proc/array.c",
    "fs/namespace.c", "fs/exec.c", "fs/read_write.c", "fs/splice.c",
    "fs/aio.c", "fs/eventpoll.c", "fs/notify/inotify/inotify_fsnotify.c",
    "fs/notify/fanotify/fanotify_user.c", "fs/dcache.c", "fs/namei.c",
    "fs/open.c", "fs/fcntl.c", "fs/compat.c",
    "ipc/msg.c", "ipc/sem.c", "ipc/shm.c", "ipc/mqueue.c", "ipc/util.c",
    "security/keys/key.c", "security/keys/keyctl.c",
    "security/keys/process_keys.c", "security/keys/request_key.c",
    "security/commoncap.c", "security/selinux/hooks.c",
    "net/socket.c", "net/core/sock.c", "net/core/skbuff.c",
    "net/unix/af_unix.c", "net/packet/af_packet.c", "net/ipv4/ip_sockglue.c",
    "net/ipv4/ping.c", "net/ipv4/udp.c", "net/ipv4/tcp.c",
    "net/ipv4/netfilter/ip_tables.c", "net/ipv6/ipv6_sockglue.c",
    "net/dccp/input.c", "net/sctp/socket.c", "net/bluetooth/sco.c",
    "net/netfilter/nf_conntrack_core.c", "net/netfilter/xt_socket.c",
    "drivers/staging/android/binder.c",
    "drivers/staging/android/ashmem.c",
    "drivers/staging/android/ion/ion.c",
    "drivers/tty/n_tty.c", "drivers/char/random.c",
]


def sha(p: Path):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def delta(a: Path, b: Path):
    """(added, removed) via git's diff, or None if equal/unavailable."""
    if not a.exists() or not b.exists():
        return None
    r = subprocess.run(
        ["git", "diff", "--no-index", "--numstat", "--no-color", str(a), str(b)],
        capture_output=True, text=True, errors="replace"
    )
    out = r.stdout.strip().splitlines()
    if not out:
        return (0, 0)
    parts = out[0].split()
    if len(parts) < 2 or parts[0] == "-":
        return (-1, -1)
    return (int(parts[0]), int(parts[1]))


rows = []
for rel in FILES:
    vp = VENDOR / rel
    if not vp.exists():
        continue
    hv, h54, h108 = sha(vp), sha(V54 / rel), sha(V108 / rel)
    if h54 is not None and hv == h54:
        s54 = "= 3.10.54"
    else:
        d = delta(V54 / rel, vp)
        s54 = "absent" if h54 is None else (f"+{d[0]}/-{d[1]}" if d else "?")
    if h108 is not None and hv == h108:
        s108 = "= 3.10.108"
    else:
        d = delta(V108 / rel, vp)
        s108 = "absent" if h108 is None else (f"+{d[0]}/-{d[1]}" if d else "?")
    rows.append((rel, vp.stat().st_size, s54, s108))

lines = []
lines.append(f"{'fichier':56} {'octets':>8}  {'vs 3.10.54':>12}  {'vs 3.10.108':>12}")
lines.append("-" * 96)
for rel, n, s54, s108 in rows:
    lines.append(f"{rel:56} {n:8}  {s54:>12}  {s108:>12}")

ident54 = [r[0] for r in rows if r[2] == "= 3.10.54"]
ident108 = [r[0] for r in rows if r[3] == "= 3.10.108"]
lines.append("")
lines.append(f"examines={len(rows)}  identiques_3.10.54={len(ident54)}  identiques_3.10.108={len(ident108)}")
lines.append("")
lines.append("== identiques a 3.10.54 (aucun correctif stable 3.10.55..3.10.108) ==")
for f in ident54:
    lines.append("  " + f)

text = "\n".join(lines)
print(text)
(AUDIT / "analysis" / "upstream-diff.txt").write_text(text, encoding="utf-8")
