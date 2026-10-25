#!/system/bin/sh
# GhostLock late boot marker (Magisk service.d hook).
# Records that userspace came up after the boot that ran blackbox.sh.

GL=/data/local/tmp/gl
dir=$(cat "$GL/current_boot" 2>/dev/null)
[ -d "$dir" ] || exit 0

{
    echo "date=$(date +%Y%m%d-%H%M%S 2>/dev/null)"
    echo "uptime=$(cat /proc/uptime 2>/dev/null)"
    echo "boot_completed=$(getprop sys.boot_completed 2>/dev/null)"
    echo "bootanim=$(getprop init.svc.bootanim 2>/dev/null)"
} > "$dir/boot_ok.txt" 2>/dev/null

cp "$dir/boot_ok.txt" "$GL/last_boot_ok" 2>/dev/null
exit 0
