# Launcher and Settings troubleshooting

Adapted from [mhabou's 688806320 port](https://github.com/mhabou/ghostlock-firetv-tank-688806320/tree/688806320).
These are community observations on that build, not a maintainer hardware test
campaign. Keep ADB access available while changing launcher components.

## Check the environment first

Use Python **3.9+**, as required by this repository, and make sure `adb` is on
PATH (or set the `ADB` environment variable to its executable). Check the build
without running the exploit:

```bash
python --version
python scripts/gl_root.py --serial <serial> --dry-run
```

`SecurityException` with `uid=2000` means that particular package operation is
not permitted from a plain ADB shell. For an intended change on your own device,
run it through `gl_root.py --cmd "..."` to execute it in the root child.

## Keep Settings while using a replacement launcher

The Amazon launcher package also contains Settings. Disabling the whole
`com.amazon.tv.launcher` package can therefore break access to Settings.
Install and verify your replacement launcher before changing the Amazon one.
Keep the package enabled and disable only its home component:

```bash
python scripts/gl_root.py --serial <serial> --cmd "pm enable com.amazon.tv.launcher; pm disable com.amazon.tv.launcher/.ui.HomeActivity_vNext"
```

mhabou reports that `pm disable` worked for this component where `disable-user`
did not. Check `adb shell pm dump com.amazon.tv.launcher` for the component's
actual state and check HOME and Settings again after rebooting. If Amazon home
still returns, the fork reports disabling `com.amazon.firehomestarter` as well:

```bash
python scripts/gl_root.py --serial <serial> --cmd "pm disable-user com.amazon.firehomestarter"
```

To restore Amazon home:

```bash
python scripts/gl_root.py --serial <serial> --cmd "pm enable com.amazon.tv.launcher; pm enable com.amazon.tv.launcher/.ui.HomeActivity_vNext; pm enable com.amazon.firehomestarter"
```

## Settings crashes after debloating

The fork reports Settings problems after disabling `com.amazon.webview.chromium`,
`com.amazon.prism.android.service` or `com.amazon.logan`. If you disabled them,
restore them and check Settings again:

```bash
python scripts/gl_root.py --serial <serial> --cmd "pm enable com.amazon.webview.chromium; pm enable com.amazon.prism.android.service; pm enable com.amazon.logan"
```

## Root and SELinux after reboot

The root command runs in a child of the exploit's privileged thread. Use the PC
CLI to capture its output; a diagnostic about that thread is not proof that
your original ADB shell became root. The binary does accept `-c` directly, but
the CLI adds build checks, logging and retry handling.

SELinux remains permissive after success until reboot. Root sessions and
temporary CPU governor changes do not survive reboot; package state changes
can persist. GhostLock does not install Magisk or a persistent root service.
