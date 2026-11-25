"""Registry resolution, identity verification and the boot-capability gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import devices
from tests import fixtures


class DeviceResolutionTests(unittest.TestCase):
    def test_resolve_by_display_name_model_codename_and_alias(self) -> None:
        for query in (
            "Samsung Galaxy A52s 5G",
            "Galaxy A52s 5G",
            "SM-A528B",
            "SM-A528B/DS",
            "a52sxq",
            "A52s",
        ):
            with self.subTest(query=query):
                spec = devices.resolve(query)
                self.assertEqual(spec.codename, "a52sxq")
                self.assertTrue(spec.known)

    def test_unknown_device_is_not_silently_accepted(self) -> None:
        spec = devices.resolve("not-a-real-phone")
        self.assertFalse(spec.known)
        self.assertEqual(spec.codename, "not-a-real-phone")
        ok, reasons = devices.verify_identity(spec, {"ro.product.device": "a52sxq"})
        self.assertFalse(ok)
        self.assertTrue(reasons)
        cap = devices.capability(
            spec,
            fastboot_seen=True,
            fastboot_vars={"unlocked": "yes", "product": "not-a-real-phone"},
        )
        self.assertFalse(cap.supported)


class IdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = devices.resolve("a52sxq")

    def test_correct_props_verify(self) -> None:
        props = {
            "ro.product.device": "a52sxq",
            "ro.product.model": "SM-A528B",
            "ro.boot.hardware": "sm7325",
            "ro.board.platform": "sm7325",
        }
        ok, reasons = devices.verify_identity(self.spec, props)
        self.assertTrue(ok, reasons)
        self.assertEqual(devices.identity_from_props(props)["ro.product.model"], "SM-A528B")

    def test_wrong_props_are_a_refusal(self) -> None:
        props = {
            "ro.product.device": "some-other-phone",
            "ro.product.model": "SM-S918B",
            "ro.board.platform": "other-soc",
        }
        ok, reasons = devices.verify_identity(self.spec, props)
        self.assertFalse(ok)
        self.assertTrue(any("ro.product.device" in reason for reason in reasons))
        self.assertTrue(any("ro.product.model" in reason for reason in reasons))

    def test_missing_identity_is_a_refusal(self) -> None:
        ok, reasons = devices.verify_identity(self.spec, {"ro.build.version.release": "14"})
        self.assertFalse(ok)
        self.assertTrue(any("no product identity" in reason for reason in reasons))


class CapabilityTests(unittest.TestCase):
    def test_a52sxq_stays_unsupported_even_with_a_fastboot_device_present(self) -> None:
        spec = devices.resolve("a52sxq")
        cap = devices.capability(
            spec,
            fastboot_seen=True,
            fastboot_vars={"unlocked": "yes", "product": "a52sxq"},
        )
        self.assertFalse(cap.supported)
        self.assertIn("no fastboot protocol", cap.reason.lower())
        self.assertIn("TWRP", cap.reason)
        self.assertIn("persistent boot partition", cap.reason)
        self.assertFalse(cap.checks["documented_fastboot_boot"])
        self.assertTrue(cap.checks["alternate_boot_path_writes_persistent_storage"])
        self.assertEqual(cap.checks["bootloader_kind"], "samsung-download")

    def test_hypothetical_fastboot_device_gate(self) -> None:
        spec = fixtures.synth_spec()
        good = devices.capability(
            spec,
            fastboot_seen=True,
            fastboot_vars={"unlocked": "yes", "product": "synthphone"},
        )
        self.assertTrue(good.supported, good.reason)

        locked = devices.capability(
            spec,
            fastboot_seen=True,
            fastboot_vars={"unlocked": "no", "product": "synthphone"},
        )
        self.assertFalse(locked.supported)
        self.assertIn("locked", locked.reason.lower())

        mismatched = devices.capability(
            spec,
            fastboot_seen=True,
            fastboot_vars={"unlocked": "yes", "product": "another-phone"},
        )
        self.assertFalse(mismatched.supported)
        self.assertIn("product", mismatched.reason.lower())

        absent = devices.capability(
            spec,
            fastboot_seen=False,
            fastboot_vars={"unlocked": "yes", "product": "synthphone"},
        )
        self.assertFalse(absent.supported)
        self.assertIn("fastboot mode", absent.reason.lower())


if __name__ == "__main__":
    unittest.main()
