"""OTA selection tests: `fetch_boot.py --build X` must pick X's package.

No network: only the static table and the artifact naming are checked. The
real fetch is exercised manually (see docs/BUILD-688806320.md).
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_boot  # noqa: E402
import tank_builds  # noqa: E402


class OtaSelectionTests(unittest.TestCase):
    def test_both_builds_have_an_ota(self) -> None:
        self.assertEqual(set(tank_builds.OTA_URLS), {"688805020", "688806320"})

    def test_url_matches_its_build(self) -> None:
        for build, url in tank_builds.OTA_URLS.items():
            with self.subTest(build=build):
                self.assertTrue(url.startswith("https://"))
                self.assertTrue(url.endswith(f"user_{build}.bin"))

    def test_default_build_is_the_original_one(self) -> None:
        self.assertEqual(tank_builds.DEFAULT_BUILD, "688805020")
        self.assertIn(tank_builds.DEFAULT_BUILD, tank_builds.OTA_URLS)

    def test_fetch_uses_the_shared_table(self) -> None:
        self.assertIs(fetch_boot.OTA_URLS, tank_builds.OTA_URLS)
        self.assertEqual(fetch_boot.DEFAULT_BUILD, tank_builds.DEFAULT_BUILD)

    def test_supported_incrementals_are_exact(self) -> None:
        self.assertEqual(
            tank_builds.SUPPORTED_INCREMENTALS,
            frozenset({"288.6.8.8_user_688805020",
                       "288.6.8.8_user_688806320"}),
        )

    def test_build_argument_accepts_both_and_rejects_others(self) -> None:
        parser = _parser()
        self.assertEqual(parser.parse_args(["--build", "688806320"]).build,
                         "688806320")
        self.assertEqual(parser.parse_args(["--build", "688805020"]).build,
                         "688805020")
        self.assertEqual(parser.parse_args([]).build, tank_builds.DEFAULT_BUILD)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["--build", "688809999"])


def _parser():
    """Rebuild the CLI parser without calling main() (which would fetch)."""

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--build", choices=tuple(tank_builds.OTA_URLS),
                        default=tank_builds.DEFAULT_BUILD)
    parser.add_argument("--dest", type=Path, default=REPO / "firmware")
    return parser


if __name__ == "__main__":
    unittest.main()
