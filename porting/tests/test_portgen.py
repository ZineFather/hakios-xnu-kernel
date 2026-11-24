"""Port generation is idempotent and never clobbers a local edit."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import portgen
from tests import fixtures


class PortgenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ports = Path(self.tmp.name) / "devices"
        self.spec = fixtures.synth_spec()

    def hashes(self, port: Path) -> dict:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in port.iterdir()
            if path.is_file()
        }

    def test_generate_twice_is_idempotent(self) -> None:
        first = portgen.generate(self.spec, self.ports)
        self.assertEqual(set(first.created), set(portgen.GENERATED))
        self.assertEqual(first.skipped_modified, [])
        port = self.ports / self.spec.codename
        names = set(self.hashes(port))
        hashes = self.hashes(port)

        second = portgen.generate(self.spec, self.ports)
        self.assertEqual(second.created, [])
        self.assertEqual(set(second.unchanged), set(portgen.GENERATED))
        self.assertEqual(second.skipped_modified, [])
        self.assertEqual(set(self.hashes(port)), names)
        self.assertEqual(self.hashes(port), hashes)

    def test_local_edit_is_skipped_and_force_overwrites_it(self) -> None:
        portgen.generate(self.spec, self.ports)
        port = self.ports / self.spec.codename
        board = port / "board.dts"
        edited = board.read_text(encoding="utf-8") + "\n// hand-edited by a human\n"
        board.write_text(edited, encoding="utf-8")
        edited_hash = hashlib.sha256(board.read_bytes()).hexdigest()
        other_hashes = {
            name: digest for name, digest in self.hashes(port).items() if name != "board.dts"
        }

        skipped = portgen.generate(self.spec, self.ports)
        self.assertIn("board.dts", skipped.skipped_modified)
        self.assertEqual(board.read_text(encoding="utf-8"), edited)
        self.assertEqual(hashlib.sha256(board.read_bytes()).hexdigest(), edited_hash)
        self.assertEqual(
            {name: digest for name, digest in self.hashes(port).items() if name != "board.dts"},
            other_hashes,
        )

        forced = portgen.generate(self.spec, self.ports, force=True)
        self.assertIn("board.dts (forced)", forced.created)
        self.assertEqual(forced.skipped_modified, [])
        self.assertEqual(
            board.read_text(encoding="utf-8"),
            portgen.GENERATED["board.dts"](self.spec),
        )

    def test_validate_rejects_a_board_with_the_wrong_name(self) -> None:
        portgen.generate(self.spec, self.ports)
        port = self.ports / self.spec.codename
        board = port / "board.dts"
        text = board.read_text(encoding="utf-8")
        board.write_text(
            text.replace(
                'name = "' + self.spec.codename + '"',
                'name = "wrongboard"',
            ),
            encoding="utf-8",
        )
        issues = portgen.validate(self.spec, port)
        self.assertTrue(
            any("wrongboard" in issue and self.spec.codename in issue for issue in issues),
            issues,
        )

    def test_manifest_round_trip_and_sha256_bytes(self) -> None:
        portgen.generate(self.spec, self.ports)
        port = self.ports / self.spec.codename
        manifest = portgen.load_manifest(port)
        self.assertIn("board.dts", manifest)
        self.assertEqual(
            manifest["board.dts"],
            portgen.sha256_bytes((port / "board.dts").read_bytes()),
        )
        portgen.save_manifest(port, manifest)
        self.assertEqual(portgen.load_manifest(port), manifest)


if __name__ == "__main__":
    unittest.main()
