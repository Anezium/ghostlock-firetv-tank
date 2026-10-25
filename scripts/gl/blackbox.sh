#!/system/bin/sh
# GhostLock black box (Magisk post-fs-data.d hook).
#
# /proc/last_kmsg on this MTK kernel is a stable snapshot of the PREVIOUS
# boot's kernel log (captured at console_initcall, see
# drivers/misc/mediatek/ram_console/mtk_ram_console.c). It therefore contains
# the full log of the boot that crashed, including the oops and its backtrace.
#
# This hook must run once per boot, before the next reboot overwrites the
# snapshot. It never touches partitions and never reboots anything.

GL=/data/local/tmp/gl
MODE="$1"

mkdir -p "$GL/runs" 2>/dev/null

seq=$(cat "$GL/boot_seq" 2>/dev/null)
[ -n "$seq" ] || seq=0
seq=$((seq + 1))
echo "$seq" > "$GL/boot_seq" 2>/dev/null

ts=$(date +%Y%m%d-%H%M%S 2>/dev/null)
[ -n "$ts" ] || ts="noseq"

if [ "$MODE" = "manual" ]; then
    dir="$GL/runs/manual-$ts-$seq"
else
    dir="$GL/runs/boot-$ts-$seq"
fi

mkdir -p "$dir" 2>/dev/null
echo "$dir" > "$GL/current_boot" 2>/dev/null

# Previous boot kernel log (the crash oracle).
if [ -r /proc/last_kmsg ]; then
    cat /proc/last_kmsg > "$dir/last_kmsg.txt" 2>"$dir/last_kmsg.err"
    echo "ok" > "$dir/last_kmsg.rc"
else
    echo "unreadable" > "$dir/last_kmsg.rc"
fi

# Context: exact build, kernel, boot reason, SELinux state.
getprop > "$dir/getprop.txt" 2>/dev/null
cat /proc/version > "$dir/version.txt" 2>/dev/null
cat /proc/cmdline > "$dir/cmdline.txt" 2>/dev/null
cat /proc/uptime > "$dir/uptime.txt" 2>/dev/null
cat /sys/fs/selinux/enforce > "$dir/selinux_enforce.txt" 2>/dev/null
cat /proc/sys/kernel/panic_on_oops > "$dir/panic_on_oops.txt" 2>/dev/null
cat /proc/sys/kernel/kptr_restrict > "$dir/kptr_restrict.txt" 2>/dev/null

# If a bench run was in flight when the device rebooted, attach it to this
# boot directory so the PC can correlate crash -> payload.
if [ -f "$GL/pending" ]; then
    cp "$GL/pending" "$dir/pending.json" 2>/dev/null
    echo "pending" > "$dir/had_pending"
fi

sync
exit 0
