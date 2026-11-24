"""CLI exit codes and the guarantee that a refused boot sends no write command."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import cli


class CliSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def call_main(self, argv):
        """Return (exit code, stdout, stderr); argparse's help exits via SystemExit."""

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = 0 if exc.code in (None, 0) else int(exc.code)
        return code, out.getvalue(), err.getvalue()

    def test_help_exits_zero(self) -> None:
        code, out, _ = self.call_main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage: hakios_port.py", out)

    def test_inspect_writes_codename_hardware_reports_without_a_device(self) -> None:
        reports = self.root / "reports"
        audit_log = self.root / "commands.jsonl"
        code, _, _ = self.call_main(
            [
                "--codename",
                "a52sxq",
                "inspect",
                "--reports-dir",
                str(reports),
                "--audit-log",
                str(audit_log),
            ]
        )
        self.assertEqual(code, 0)

        md_path = reports / "a52sxq_hardware_report.md"
        json_path = reports / "a52sxq_hardware_report.json"
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertFalse(payload["device_present"])
        self.assertEqual(payload["spec"]["codename"], "a52sxq")
        self.assertIn("No device was inspected", md_path.read_text(encoding="utf-8"))
        self.assertFalse(audit_log.exists(), "inspection must not issue a device command")

    def test_a52sxq_boot_dry_run_exits_three_without_a_flash_verb(self) -> None:
        reports = self.root / "reports"
        audit_log = self.root / "commands.jsonl"
        code, _, _ = self.call_main(
            [
                "--device",
                "Samsung Galaxy A52s 5G",
                "boot",
                "--dry-run",
                "--reports-dir",
                str(reports),
                "--audit-log",
                str(audit_log),
            ]
        )
        self.assertEqual(code, 3)

        result_path = reports / "boot-result.json"
        self.assertTrue(result_path.is_file())
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["error"], "UnsupportedHardware")
        self.assertFalse(payload["started"])
        self.assertFalse(payload["capability"]["supported"])

        log_text = audit_log.read_text(encoding="utf-8") if audit_log.exists() else ""
        self.assertNotRegex(
            log_text,
            r"\b(?:flash|flashall|erase|format|set_active|partition|resize|oem\s+unlock|"
            r"flashing\s+unlock|-w)\b",
            "a refused boot must not record a write verb",
        )


if __name__ == "__main__":
    unittest.main()
