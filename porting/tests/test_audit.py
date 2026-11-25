"""Storage-write classification, command-log replay and loader checks."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import audit
from tests import fixtures


class AuditScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "workflow.sh"
        self.source.write_text(
            "\n".join(
                (
                    "fastboot flash boot boot.img",
                    "logdump",
                    "ufs_write=1",
                    "fastboot boot selected.img",
                    "adb push x y",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.findings = audit.scan_file(self.source)

    def finding(self, needle: str) -> audit.Finding:
        matches = [item for item in self.findings if needle in item.text]
        self.assertEqual(len(matches), 1, [item.text for item in self.findings])
        return matches[0]

    def test_all_five_lines_are_classified(self) -> None:
        self.assertEqual(len(self.findings), 5)
        for needle, category, severity in (
            ("fastboot flash boot", audit.PERSISTENT, "critical"),
            ("logdump", audit.PERSISTENT, "critical"),
            ("ufs_write", audit.PERSISTENT, "warning"),
            ("fastboot boot", audit.RAM, "info"),
            ("adb push", audit.PERSISTENT, "critical"),
        ):
            with self.subTest(needle=needle):
                found = self.finding(needle)
                self.assertEqual(found.category, category)
                self.assertEqual(found.severity, severity)

    def test_raw_flash_has_an_unmitigated_critical_count(self) -> None:
        flash = self.finding("fastboot flash boot")
        self.assertFalse(flash.mitigated)
        summary = audit.summarize([flash])
        self.assertEqual(summary["unmitigated_persistent"], 1)
        self.assertEqual(summary["counts"][audit.PERSISTENT], 1)

    def test_guarded_logdump_and_ufs_write_have_zero_unmitigated(self) -> None:
        guarded = [self.finding("logdump"), self.finding("ufs_write")]
        self.assertTrue(all(item.mitigated for item in guarded))
        summary = audit.summarize(guarded)
        self.assertEqual(summary["unmitigated_persistent"], 0)

        whole = audit.summarize(self.findings)
        self.assertEqual(whole["unmitigated_persistent"], 2)  # flash + adb push
        self.assertEqual(whole["counts"][audit.RAM], 1)

    def test_scan_tree_finds_the_source_but_skips_test_dirs(self) -> None:
        findings = audit.scan_tree(self.root)
        self.assertTrue(any("workflow.sh" in item.path for item in findings))
        self.assertTrue(all(not Path(item.path).is_absolute() for item in findings))
        (self.root / "tests").mkdir()
        hidden = self.root / "tests" / "ignored.sh"
        hidden.write_text("fastboot flash boot x.img\n", encoding="utf-8")
        self.assertFalse(any("ignored.sh" in item.path for item in audit.scan_tree(self.root)))

    def test_missing_command_log_report_does_not_include_its_local_path(self) -> None:
        ok, problems = audit.verify_command_log(self.root / "commands.jsonl")
        self.assertTrue(ok)
        self.assertIn("no device commands were recorded", problems[0])
        self.assertNotIn(str(self.root), problems[0])


class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_command_log_accepts_allowed_jsonl_records(self) -> None:
        image = self.root / "boot.img"
        image.write_bytes(b"local image")
        path = self.root / "commands.jsonl"
        records = (
            {"kind": "adb", "argv": ["adb", "-s", "SERIAL", "shell", "getprop"]},
            {"kind": "fastboot", "argv": ["fastboot", "getvar", "product"]},
            {"kind": "fastboot", "argv": ["fastboot", "boot", str(image)]},
            {"kind": "host", "argv": ["python", "tools/boards.py", "check"]},
        )
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        ok, problems = audit.verify_command_log(path)
        self.assertTrue(ok, problems)

    def test_command_log_rejects_a_recorded_flash(self) -> None:
        path = self.root / "commands.jsonl"
        path.write_text(
            json.dumps({"kind": "fastboot", "argv": ["fastboot", "flash", "boot", "x.img"]}) + "\n",
            encoding="utf-8",
        )
        ok, problems = audit.verify_command_log(path)
        self.assertFalse(ok)
        self.assertTrue(problems)
        self.assertTrue(any("flash" in problem for problem in problems))

    def test_bootargs_verify_bad_and_clean_cmdlines(self) -> None:
        for arg in ("ufs_write=1", "var_store=1", "var_hfs=/x", "root_apfs=/x", "dsu_write=1"):
            with self.subTest(arg=arg):
                ok, bad = audit.verify_bootargs("console=ttyS0 " + arg)
                self.assertFalse(ok)
                self.assertIn(arg, bad)
        ok, bad = audit.verify_bootargs("console=ttyS0 quiet")
        self.assertTrue(ok, bad)
        self.assertEqual(bad, [])

    def test_loader_binary_with_utf16le_logdump_is_rejected(self) -> None:
        clean = self.root / "loader-clean.efi"
        clean.write_bytes(b"\x00\x01SYNTHETIC-EFI")
        ok, detail = audit.verify_loader_binary(clean)
        self.assertTrue(ok, detail)

        dirty = self.root / "loader-dirty.efi"
        dirty.write_bytes(b"\x00\x01" + "logdump".encode("utf-16-le") + b"\x00\x00")
        ok, detail = audit.verify_loader_binary(dirty)
        self.assertFalse(ok)
        self.assertIn("UTF-16LE", detail)


if __name__ == "__main__":
    unittest.main()
