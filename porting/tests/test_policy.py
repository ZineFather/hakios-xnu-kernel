"""Default-deny command policy: only read-only queries and one local boot file."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import policy
from hakiosport.errors import PolicyViolation


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "boot.img"
        self.image.write_bytes(b"a local image")
        self.previous_cwd = Path.cwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.root)

    def test_read_only_fastboot_and_adb_allowed(self) -> None:
        for argv in (
            ["devices"],
            ["version"],
            ["--version"],
            ["getvar", "all"],
            ["getvar", "product"],
            ["getvar", "unlocked"],
            ["reboot"],
        ):
            with self.subTest(fastboot=argv):
                self.assertEqual(policy.check_fastboot(argv), argv)
        for argv, expected in (
            (["devices", "-l"], ["devices", "-l"]),
            (["version"], ["version"]),
            (["get-state"], ["get-state"]),
            (["shell", "getprop"], ["shell", "getprop"]),
            (["shell", "cat", "/proc/cpuinfo"], ["shell", "cat", "/proc/cpuinfo"]),
            (["shell", "wm", "size"], ["shell", "wm", "size"]),
            (["shell", "dumpsys", "battery"], ["shell", "dumpsys", "battery"]),
            (["shell", "logcat", "-d"], ["shell", "logcat", "-d"]),
            # The returned vector has the tool and serial removed; the runner adds them.
            (["-s", "SERIAL", "shell", "getprop"], ["shell", "getprop"]),
            (
                ["pull", "/proc/version", str(self.root / "version.txt")],
                ["pull", "/proc/version", str(self.root / "version.txt")],
            ),
        ):
            with self.subTest(adb=argv):
                self.assertEqual(policy.check_adb(argv), expected)

    def test_every_forbidden_fastboot_verb_refused(self) -> None:
        cases = (
            ["flash", "boot", str(self.image)],
            ["flashall"],
            ["erase", "boot"],
            ["format", "userdata"],
            ["set_active", "a"],
            ["partition", "system:1M"],
            ["resize", "super"],
            ["oem", "unlock"],
            ["flashing", "unlock"],
            ["-w"],
            ["--wipe"],
            ["sideload", "x.zip"],
            ["update", "x.zip"],
            ["wipe", "userdata"],
            ["reboot-bootloader"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(argv)

    def test_unknown_fastboot_verbs_are_refused_by_default(self) -> None:
        for argv in (["help"], ["continue"], ["bootloader"], ["flashboot"]):
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(argv)

    def test_boot_requires_exactly_one_existing_local_file(self) -> None:
        # setUp chdir's into an empty temp directory containing only boot.img.
        self.assertEqual(policy.check_fastboot(["boot", "boot.img"]), ["boot", "boot.img"])
        for argv in (
            [],
            ["boot"],
            ["boot", "boot.img", "boot.img"],
            ["boot", "missing.img"],
            ["boot", "."],
            ["boot", "-s", "boot.img"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(argv)

    def test_windows_absolute_local_image_path_is_accepted(self) -> None:
        # An absolute path is still "an existing local file" on the stated Windows
        # host.  This assertion stays strict: it currently exposes a module bug in
        # policy._looks_like_local_file() (the drive-letter colon is treated as
        # partition syntax).  See the test report for the precise failure.
        self.assertEqual(
            policy.check_fastboot(["boot", str(self.image)]),
            ["boot", str(self.image)],
        )

    def test_partition_like_boot_names_refused(self) -> None:
        # setUp chdir's into the empty temp directory, so a coincidental host file
        # called "boot" cannot make a partition name look like a local image.
        for name in ("boot", "boot_a", "boot:foo", "boot_a:foo"):
            with self.subTest(name=name):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(["boot", name])

    def test_global_serial_prefix_is_accepted_only_with_a_value(self) -> None:
        self.assertEqual(
            policy.check_fastboot(["-s", "SERIAL", "getvar", "product"]),
            ["getvar", "product"],
        )
        self.assertEqual(
            policy.check_fastboot(["-s", "SERIAL", "boot", "boot.img"]),
            ["boot", "boot.img"],
        )
        for argv in (["-s"], ["-s", "SERIAL"], ["-u", "devices"], ["-w", "devices"]):
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(argv)

    def test_non_read_only_getvars_and_fetch_refused(self) -> None:
        for argv in (
            ["getvar", "some-write-only-name"],
            ["getvar", "wipe"],
            ["getvar", "product", "extra"],
            ["fetch", "boot", "out.img"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_fastboot(argv)

    def test_adb_shell_metacharacter_injection_refused(self) -> None:
        for command in (
            "getprop; id",
            "getprop | id",
            "getprop > /data/local/tmp/x",
            "getprop `id`",
            "getprop\nid",
            "getprop $(id)",
            "getprop & id",
        ):
            with self.subTest(command=command):
                with self.assertRaises(PolicyViolation):
                    policy.check_adb(["shell", command])

    def test_adb_shell_write_and_privilege_commands_refused(self) -> None:
        for command in (
            "su",
            "dd if=/dev/zero of=/data/x",
            "rm -rf /data",
            "setprop persist.foo 1",
            "mount -o remount /",
            "sh -c 'cat /data/x'",
            "reboot",
        ):
            with self.subTest(command=command):
                with self.assertRaises(PolicyViolation):
                    policy.check_adb(["shell", command])

    def test_adb_push_root_and_writes_outside_read_only_shell_refused(self) -> None:
        for argv in (
            ["push", "x", "y"],
            ["root"],
            ["remount"],
            ["sideload", "x.zip"],
            ["install", "x.apk"],
            ["shell", "settings", "put", "system", "x", "y"],
            ["shell", "pm", "install", "x.apk"],
            ["pull", "data/data/x", str(self.root / "x")],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(PolicyViolation):
                    policy.check_adb(argv)

    def test_policy_description_names_the_refusals(self) -> None:
        text = policy.describe_policy()
        self.assertIn("boot <local file>", text)
        self.assertIn("read-only", text)
        self.assertIn("Refused, always", text)


if __name__ == "__main__":
    unittest.main()
