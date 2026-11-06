"""Build-guard tests: the payload must never run on an unverified build.

These tests use a fake `Device`; they need neither ADB nor hardware. They
check the decision logic only — that the two supported incrementals pass and
anything else is refused before a push or an exec.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import gl_bench  # noqa: E402
from gl_bench import BenchError, Device, require_build  # noqa: E402

KERNEL_6320 = (
    "Linux version 3.10.54+ (build@i3-ri-14-use1a-b-16-04-fos-17) "
    "(gcc version 4.8 (GCC) ) #1 SMP PREEMPT Sun Apr 27 22:14:52 UTC 2025"
)
KERNEL_5020 = (
    "Linux version 3.10.54+ (build@i3-ri-14-use1a-b-16-04-fos-6) "
    "(gcc version 4.8 (GCC) ) #1 SMP PREEMPT Wed Mar 13 02:16:25 UTC 2024"
)


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["fake"], returncode=returncode,
                                       stdout=stdout, stderr="")


class FakeDevice(Device):
    """Minimal stand-in: answers by command string, never touches adb."""

    def __init__(self, *, incremental: str, device: str = "tank",
                 kernel: str = KERNEL_6320, root: bool = False) -> None:
        super().__init__("fake-serial")
        self.props_map = {
            "ro.build.version.incremental": incremental,
            "ro.product.device": device,
            "ro.build.fingerprint": "Amazon/tank/tank:5.2.9.5/...",
        }
        self.kernel = kernel
        self.root = root

    def shell(self, cmd: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
        if cmd == "getprop":
            return completed("\n".join(
                f"[{key}]: [{value}]" for key, value in self.props_map.items()))
        if cmd == "cat /proc/version":
            return completed(self.kernel + "\n")
        if cmd == "getenforce":
            return completed("Enforcing\n")
        if cmd == "cat /proc/sys/kernel/panic_on_oops":
            return completed("1\n")
        return completed("", returncode=1)

    def su(self, cmd: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
        if cmd == "cat /proc/sys/kernel/kptr_restrict":
            return completed("2\n")
        if cmd == "id":
            return completed("uid=0(root) gid=0(root)\n" if self.root
                            else "uid=2000(shell) gid=2000(shell)\n")
        return completed("", returncode=1)


class BuildGuardTests(unittest.TestCase):
    def test_both_supported_builds_pass(self) -> None:
        for build in ("688805020", "688806320"):
            with self.subTest(build=build):
                dev = FakeDevice(incremental=f"288.6.8.8_user_{build}")
                values = require_build(dev)
                self.assertEqual(values["incremental"], f"288.6.8.8_user_{build}")

    def test_unknown_build_is_refused(self) -> None:
        dev = FakeDevice(incremental="288.6.8.8_user_689000000")
        with self.assertRaises(BenchError) as ctx:
            require_build(dev)
        message = str(ctx.exception)
        self.assertIn("incremental", message)
        self.assertIn("288.6.8.8_user_688806320", message)

    def test_prefix_of_supported_build_is_refused(self) -> None:
        dev = FakeDevice(incremental="288.6.8.8_user_68880632")
        with self.assertRaises(BenchError):
            require_build(dev)

    def test_wrong_product_is_refused(self) -> None:
        dev = FakeDevice(incremental="288.6.8.8_user_688806320", device="sloane")
        with self.assertRaises(BenchError) as ctx:
            require_build(dev)
        self.assertIn("device", str(ctx.exception))

    def test_kernel_banner_without_plus_is_refused(self) -> None:
        dev = FakeDevice(incremental="288.6.8.8_user_688806320",
                         kernel="Linux version 3.10.54 (build@host) #1 SMP")
        with self.assertRaises(BenchError) as ctx:
            require_build(dev)
        self.assertIn("kernel", str(ctx.exception))

    def test_kernel_banner_of_the_other_build_passes(self) -> None:
        for kernel in (KERNEL_5020, KERNEL_6320):
            with self.subTest(kernel=kernel[:40]):
                dev = FakeDevice(incremental="288.6.8.8_user_688805020",
                                 kernel=kernel)
                self.assertEqual(require_build(dev)["kernel"], kernel)

    def test_guard_is_prefix_anchored(self) -> None:
        # 3.10.540+ must not match "3.10.54+".
        dev = FakeDevice(incremental="288.6.8.8_user_688806320",
                         kernel="Linux version 3.10.540+ (build@host)")
        with self.assertRaises(BenchError):
            require_build(dev)

    def test_supported_set_matches_ota_table(self) -> None:
        import tank_builds

        self.assertEqual(gl_bench.SUPPORTED_INCREMENTALS,
                         tank_builds.SUPPORTED_INCREMENTALS)


if __name__ == "__main__":
    unittest.main()
