"""The boot gate: unsupported hardware refuses before any device command."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import boot, devices
from hakiosport.errors import PolicyViolation, UnsupportedHardware, UsageError
from hakiosport.runner import CommandRunner
from tests import fixtures


def capable_detection(spec, *, unlocked: str = "yes", product: str | None = None) -> boot.Detection:
    """A snapshot saying a fastboot device is present, as observed externally."""

    return boot.Detection(
        fastboot_available=True,
        fastboot_state="device",
        fastboot_serial="TESTSERIAL",
        fastboot_vars={"unlocked": unlocked, "product": product or spec.codename},
    )


class BootRefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audit_path = self.root / "commands.jsonl"
        self.runner = CommandRunner(audit_path=self.audit_path, dry_run=True)
        # No tools on PATH means detection records notes and issues zero commands.
        self.runner.adb_path = None
        self.runner.fastboot_path = None
        self.a52sxq = devices.resolve("a52sxq")

    def test_a52sxq_refuses_without_an_image_and_without_a_device_command(self) -> None:
        absent_image = self.root / "does-not-exist.img"
        with self.assertRaises(UnsupportedHardware) as caught:
            boot.boot(self.runner, self.a52sxq, absent_image, log_dir=self.root / "logs")
        self.assertIn("no fastboot protocol", caught.exception.message.lower())
        self.assertIn("TWRP", caught.exception.message)
        self.assertIn("persistent boot partition", caught.exception.message)
        self.assertEqual(self.runner.records, [])
        self.assertFalse(self.audit_path.exists())

    def test_detect_with_no_tools_returns_notes_not_exceptions(self) -> None:
        detection = boot.detect(self.runner, self.a52sxq)
        self.assertEqual(detection.adb_state, "tool-missing")
        self.assertEqual(detection.fastboot_state, "tool-missing")
        self.assertFalse(detection.adb_available)
        self.assertFalse(detection.fastboot_available)
        self.assertTrue(detection.notes)
        self.assertEqual(self.runner.records, [])

    def test_summarize_log_distinguishes_panic_from_a_clean_run(self) -> None:
        panic = boot.summarize_log(
            "Darwin Kernel Version 23.1.0\n"
            "panic(cpu 0 caller 0xffff): wait lock timeout\n"
        )
        self.assertTrue(panic["panic"])
        self.assertIn("panic(cpu", panic["panic_line"])
        self.assertTrue(panic["kernel_started"])

        clean = boot.summarize_log(
            "Darwin Kernel Version 23.1.0\n"
            "write to logdump: not written\n"
            "kernel returned: log at 0x9\n"
        )
        self.assertFalse(clean["panic"])
        self.assertTrue(clean["kernel_started"])
        self.assertTrue(clean["kernel_returned"])
        self.assertTrue(clean["write_refusals"])
        self.assertEqual(clean["errors"], [])

    def test_capable_device_missing_image_is_usage_error_before_boot(self) -> None:
        spec = fixtures.synth_spec()
        with self.assertRaises(UsageError) as caught:
            boot.boot(
                self.runner,
                spec,
                self.root / "missing.img",
                detection=capable_detection(spec),
                log_dir=self.root / "logs",
            )
        self.assertIn("does not exist", caught.exception.message)
        self.assertEqual(self.runner.records, [])

    def test_capable_device_bad_image_is_policy_violation_before_boot(self) -> None:
        spec = fixtures.synth_spec()
        bad = self.root / "bad.img"
        bad.write_bytes(b"NOTANANDROIDIMAGE" + b"\0" * 100)
        with self.assertRaises(PolicyViolation) as caught:
            boot.boot(
                self.runner,
                spec,
                bad,
                detection=capable_detection(spec),
                log_dir=self.root / "logs",
            )
        self.assertIn("invalid or write-enabling", caught.exception.message)
        self.assertEqual(self.runner.records, [])
        self.assertFalse(self.audit_path.exists())

    def test_capable_device_write_enabling_payload_is_refused_before_boot(self) -> None:
        spec = fixtures.synth_spec()
        image = fixtures.build_boot_image(
            self.root / "ufs.img",
            cmdline="console=ttyS0 ufs_write=1",
        )
        with self.assertRaises(PolicyViolation) as caught:
            boot.boot(
                self.runner,
                spec,
                image.path,
                detection=capable_detection(spec),
                log_dir=self.root / "logs",
            )
        self.assertIn("write-enabling", caught.exception.message)
        self.assertEqual(self.runner.records, [])


if __name__ == "__main__":
    unittest.main()
