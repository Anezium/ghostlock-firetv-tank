#!/system/bin/sh
# Device-side checks for the GhostLock tank bench.

GL=/data/local/tmp/gl

echo "who=$(id 2>/dev/null)"
echo "context=$(cat /proc/self/attr/current 2>/dev/null)"
echo "fingerprint=$(getprop ro.build.fingerprint 2>/dev/null)"
echo "incremental=$(getprop ro.build.version.incremental 2>/dev/null)"
echo "device=$(getprop ro.product.device 2>/dev/null)"
echo "sdk=$(getprop ro.build.version.sdk 2>/dev/null)"
echo "kernel=$(cat /proc/version 2>/dev/null)"
echo "selinux=$(getenforce 2>/dev/null)"
echo "panic_on_oops=$(cat /proc/sys/kernel/panic_on_oops 2>/dev/null)"
echo "kptr_restrict=$(cat /proc/sys/kernel/kptr_restrict 2>/dev/null)"
echo "su=$(command -v su 2>/dev/null)"
echo "hook_pfd=$([ -f /data/adb/post-fs-data.d/99-gl-blackbox.sh ] && echo yes || echo no)"
echo "hook_sd=$([ -f /data/adb/service.d/99-gl-late.sh ] && echo yes || echo no)"
echo "boot_seq=$(cat "$GL/boot_seq" 2>/dev/null)"
echo "current_boot=$(cat "$GL/current_boot" 2>/dev/null)"
echo "pending=$([ -f "$GL/pending" ] && echo yes || echo no)"
echo "ion=$(ls -l /dev/ion 2>/dev/null)"
echo "mali=$(ls -l /dev/mali 2>/dev/null)"

tmp="$GL/bin/.doctor_lk"
if cat /proc/last_kmsg > "$tmp" 2>/dev/null; then
    echo "last_kmsg=readable"
    echo "last_kmsg_stat=$(ls -l "$tmp" 2>/dev/null)"
    rm -f "$tmp" 2>/dev/null
else
    echo "last_kmsg=denied"
fi
exit 0
