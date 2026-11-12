# Independent hardware validation: tank build 688806320

Test date: 2026-11-09

## Device

| Property | Value |
|---|---|
| Device | Amazon Fire TV Stick 2nd Generation |
| Model | AFTT |
| Codename | tank |
| Android | 5.1.1 |
| Fire OS | 5.2.9.5 |
| Build | 288.6.8.8_user_688806320 |
| Kernel | Linux 3.10.54+ |
| Host | Raspberry Pi 5 |
| Connection | ADB over TCP/IP |

## Results

| Test | Result |
|---|---|
| ADB connection | PASS |
| Build guard | PASS |
| Temporary root | PASS |
| Successful root invocations | 2/2 |
| Root invocation 1 | First attempt, 0.4 s |
| Root invocation 2 | First attempt, 3.2 s |
| Root identity | uid=0(root) |
| SELinux during root execution | Permissive |
| Privileged package disabling | PASS |
| Package state persistence after reboot | PASS |
| SELinux enforcing after reboot | PASS |
| Package re-enabling | PASS |
| Package re-disabling | PASS |
| Host-side unit tests | 16/16 PASS |
| Persistent su access | Not installed |
| Long-term stability | Not tested |

## Protected package management

Unprivileged ADB package disabling initially failed
with a SecurityException.

After temporary root execution, the following packages
were successfully disabled:

- com.amazon.bueller.photos
- com.amazon.gamehub
- com.amazon.storm.lightning.tutorial
- com.amazon.tmm.tutorial

All four remained disabled after reboot.

Amazon Photos was subsequently re-enabled and
disabled again using a single privileged command.
Both state transitions were verified.

## Reboot validation

After reboot:
- SELinux returned to Enforcing.
- All four disabled packages remained disabled.
- ADB connectivity was restored.
- No persistent su binary was available.

The doctor's root check reported FAIL, as expected
without a persistent root installation.

## Limitations

This is an independent functional hardware validation,
not a statistical reliability benchmark.

Only two successful root invocations were recorded.
No kernel panic occurred during those invocations.

Long-term stability and full streaming compatibility
have not been formally validated.
