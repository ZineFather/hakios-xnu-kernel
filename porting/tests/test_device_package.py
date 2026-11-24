"""The a52sxq package must be complete, honest and free of device-write recipes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

PACKAGE = PACKAGE_ROOT / "devices" / "a52sxq"


class DevicePackageTests(unittest.TestCase):
    def test_required_package_files_exist(self) -> None:
        required = [
            "board.dts",
            "soc.dtsi",
            "device.conf",
            "README.md",
            "BUILDING.md",
            "COMPATIBILITY.md",
            "DRIVERS.md",
            "DT_NOTES.md",
            "firmware.conf",
            "build.sh",
            "configs/a52sxq.config",
            "configs/a52sxq_defconfig",
        ]
        missing = [name for name in required if not (PACKAGE / name).is_file()]
        self.assertEqual(missing, [])

    def test_readme_has_no_unfilled_template_text(self) -> None:
        text = (PACKAGE / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("One sentence: how far it boots", text)
        self.assertNotIn("| SoC | CHIP", text)
        self.assertIn("never built and never booted", text)
        self.assertIn("not tested", text)

    def test_board_does_not_claim_unverified_features(self) -> None:
        text = (PACKAGE / "board.dts").read_text(encoding="utf-8")
        self.assertIn("features = <>;", text)
        self.assertNotIn("uefi {", text)

    def test_build_script_has_no_persistent_write_command(self) -> None:
        text = (PACKAGE / "build.sh").read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastboot flash",
            "fastboot erase",
            "fastboot format",
            "fastboot set_active",
            "fastboot oem unlock",
            "fastboot flashing unlock",
            "adb push",
            "dd if=",
            "mkfs",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("hakios_port.py", text)
        self.assertIn("--dry-run", text)

    def test_device_conf_claims_nothing_works(self) -> None:
        text = (PACKAGE / "device.conf").read_text(encoding="utf-8").lower()
        self.assertNotIn("status      display     works", text)
        self.assertIn("not tested", text)
        self.assertIn("no fastboot", text)


if __name__ == "__main__":
    unittest.main()
