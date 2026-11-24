"""Synthetic Android/XNUP boot images: parsing, hashing and write-arg refusal."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import image
from tests import fixtures


class ImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_header_payload_and_sha256(self) -> None:
        fixture = fixtures.build_boot_image(
            self.root / "boot.img",
            cmdline="console=ttyS0 quiet",
            header_cmdline="header-only=1",
        )
        info = image.inspect_boot_image(fixture.path)
        self.assertTrue(info.valid, info.reasons)
        self.assertEqual(info.kind, "android")
        self.assertEqual(info.header_version, 0)
        self.assertEqual(info.page_size, 2048)
        self.assertEqual(info.kernel_size, len(fixture.kernel))
        self.assertEqual(info.ramdisk_size, len(b"SYNTHETIC-RAMDISK"))
        self.assertEqual(info.cmdline, "header-only=1")
        self.assertEqual(info.payload_entries, ["loader.efi", "cmdline"])
        self.assertEqual(info.payload_cmdline, "console=ttyS0 quiet")
        self.assertEqual(info.sha256, hashlib.sha256(fixture.blob).hexdigest())
        self.assertEqual(info.sha256, image.sha256_file(fixture.path))
        self.assertEqual(info.size, len(fixture.blob))

    def test_xnup_parser_and_payload_cmdline(self) -> None:
        fixture = fixtures.build_boot_image(self.root / "boot.img", cmdline="a=1 b=2")
        entries = image.parse_xnup(fixture.xnup)
        self.assertIsNotNone(entries)
        self.assertEqual([entry.name for entry in entries], ["loader.efi", "cmdline"])
        self.assertEqual(entries[0].data, b"SYNTHETIC-EFI")
        self.assertEqual(entries[1].data.split(b"\0", 1)[0], b"a=1 b=2")
        self.assertIsNone(image.parse_xnup(b"this is not an XNUP container" * 4))

        names, cmdline = image.find_payload_cmdline(fixture.payload)
        self.assertEqual(names, ["loader.efi", "cmdline"])
        self.assertEqual(cmdline, "a=1 b=2")

    def test_write_enabling_payload_cmdlines_are_invalid(self) -> None:
        for arg in (
            "ufs_write=1",
            "var_store=1",
            "var_hfs=/x",
            "root_apfs=/dev/disk1s1",
            "dsu_write=1",
        ):
            with self.subTest(arg=arg):
                fixture = fixtures.build_boot_image(
                    self.root / "boot.img",
                    cmdline="console=ttyS0 " + arg,
                )
                self.assertIn(arg, image.forbidden_args(fixture.cmdline))
                info = image.inspect_boot_image(fixture.path)
                self.assertFalse(info.valid, info.reasons)
                self.assertTrue(
                    any("persistent writes" in reason for reason in info.reasons),
                    info.reasons,
                )

    def test_clean_cmdline_is_allowed(self) -> None:
        fixture = fixtures.build_boot_image(self.root / "boot.img", cmdline="quiet splash")
        info = image.inspect_boot_image(fixture.path)
        self.assertTrue(info.valid, info.reasons)
        self.assertEqual(image.forbidden_args(info.payload_cmdline), [])

    def test_bad_magic_is_invalid(self) -> None:
        bad = self.root / "bad.img"
        bad.write_bytes(b"NOTANDR!" + b"\0" * 128)
        info = image.inspect_boot_image(bad)
        self.assertFalse(info.valid)
        self.assertTrue(any("not an Android boot image" in reason for reason in info.reasons))

    def test_missing_file_is_invalid(self) -> None:
        info = image.inspect_boot_image(self.root / "absent.img")
        self.assertFalse(info.valid)
        self.assertIn("file does not exist", info.reasons)

    def test_image_constants(self) -> None:
        self.assertEqual(image.XNUP_MAGIC, 0x50554E58)
        self.assertIn("ufs_write=1", image.FORBIDDEN_BOOTARGS)
        self.assertIn("dsu_write=", image.FORBIDDEN_BOOTARGS)


if __name__ == "__main__":
    unittest.main()
