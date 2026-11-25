"""CLI exit codes and the guarantee that a refused boot sends no write command."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import audit, cli, devices, inspect as inspect_mod
from hakiosport.boot import Detection
from hakiosport.inspect import HardwareReport


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
        # A read-only adb probe may be recorded when adb is installed (CI images
        # ship it), so the log can exist. What must hold is that every recorded
        # command is allowed and that no boot or write verb was issued.
        log_ok, log_problems = audit.verify_command_log(audit_log)
        self.assertTrue(log_ok, log_problems)
        if audit_log.exists():
            log_text = audit_log.read_text(encoding="utf-8")
            self.assertNotRegex(
                log_text,
                r'"argv":\s*\[[^\]]*"(?:boot|flash|flashall|erase|format|set_active|'
                r'partition|resize|oem|flashing)"',
                "inspection must not record a boot or write verb",
            )

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

    def test_inspect_saves_read_only_device_tree_under_reports(self) -> None:
        reports = self.root / "reports"
        spec = devices.resolve("a52sxq")
        ctx = SimpleNamespace(
            args=SimpleNamespace(serial=None),
            runner=object(),
            reports_dir=reports,
            spec=spec,
            out=SimpleNamespace(say=lambda *_: None, warn=lambda *_: None),
        )
        detection = Detection(
            adb_available=True,
            adb_state="device",
            adb_serial="TWRP-SERIAL",
        )
        hardware = HardwareReport(spec=spec, device_present=True)

        with patch.object(cli.boot_mod, "detect", return_value=detection):
            with patch.object(cli.inspect_mod, "collect", return_value=hardware) as collect:
                self.assertEqual(cli._cmd_inspect(ctx), 0)

        self.assertEqual(
            collect.call_args.kwargs["fdt_dir"],
            reports / "device-tree",
        )

    def test_device_tree_report_path_does_not_expose_host_root(self) -> None:
        class FakeAdb:
            def single(self, serial=None):
                return SimpleNamespace(serial="TWRP-SERIAL")

            def getprop(self, serial=None):
                return {}

            def shell(self, command, *, serial=None):
                return SimpleNamespace(ok=False, stdout="")

            def pull(self, remote, local, *, serial=None):
                Path(local).parent.mkdir(parents=True, exist_ok=True)
                Path(local).write_bytes(b"test dtb")
                return True

        reports = self.root / "reports"
        hardware = inspect_mod.collect(
            FakeAdb(),
            devices.resolve("a52sxq"),
            fdt_dir=reports / "device-tree",
        )
        self.assertEqual(
            hardware.fdt_saved,
            "device-tree/a52sxq-device-tree.dtb",
        )
        self.assertTrue(
            (reports / "device-tree" / "a52sxq-device-tree.dtb").is_file()
        )

    def test_build_dry_run_does_not_claim_artifacts_were_built(self) -> None:
        reports = self.root / "reports"
        kernel_src = PACKAGE_ROOT.parent.parent
        code, out, _ = self.call_main(
            [
                "--codename",
                "a52sxq",
                "build",
                "--dry-run",
                "--kernel-src",
                str(kernel_src),
                "--reports-dir",
                str(reports),
            ]
        )

        self.assertEqual(code, 0)
        self.assertIn(
            "Build completed: no (dry run; no artifacts were built)", out
        )
        payload = json.loads((reports / "build-report.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["completed"])


if __name__ == "__main__":
    unittest.main()
