#!/system/bin/sh
# Install the GhostLock black box as Magisk boot hooks.
# No partition is touched: only /data/local/tmp and /data/adb/*.d.

GL=/data/local/tmp/gl

mkdir -p "$GL/bin" "$GL/runs" 2>/dev/null
chmod 777 "$GL" "$GL/bin" "$GL/runs" 2>/dev/null

fail=0
cp "$GL/bin/blackbox.sh" /data/adb/post-fs-data.d/99-gl-blackbox.sh || fail=1
cp "$GL/bin/late.sh" /data/adb/service.d/99-gl-late.sh || fail=1
chmod 755 /data/adb/post-fs-data.d/99-gl-blackbox.sh 2>/dev/null
chmod 755 /data/adb/service.d/99-gl-late.sh 2>/dev/null

# Remove the probe files left by earlier diagnostics.
rm -f /data/adb/post-fs-data.d/.gl_probe /data/adb/service.d/.gl_probe 2>/dev/null

if [ "$fail" = "0" ]; then
    echo "INSTALL_OK"
else
    echo "INSTALL_FAIL"
fi
ls -l /data/adb/post-fs-data.d/99-gl-blackbox.sh /data/adb/service.d/99-gl-late.sh 2>&1
exit "$fail"
