"""A plan-only run must never be reported as a completed build."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import build
from hakiosport.errors import BuildBlocked
from hakiosport.runner import CommandRunner
from tests.fixtures import synth_spec


class BuildStatusTests(unittest.TestCase):
    def make_plan(self) -> build.BuildPlan:
        return build.BuildPlan(
            spec=synth_spec(),
            kernel_src=Path("synthetic-kernel"),
            host=build.HostInfo(
                system="Linux",
                release="test",
                machine="aarch64",
                supported=True,
            ),
            steps=[
                build.BuildStep(
                    name="validate device packages",
                    argv=["python3", "tools/boards.py", "check"],
                    cwd="synthetic-kernel",
                )
            ],
        )

    def test_dry_run_records_plan_without_claiming_build_complete(self) -> None:
        report = build.build(
            CommandRunner(),
            self.make_plan(),
            dry_run=True,
        )

        self.assertTrue(report.dry_run)
        self.assertFalse(report.completed)
        self.assertTrue(report.results[0]["dry_run"])
        self.assertTrue(report.as_dict()["dry_run"])
        self.assertFalse(report.as_dict()["completed"])

    def test_image_step_without_an_artifact_fails_the_build(self) -> None:
        class SuccessfulHostRunner:
            def host(self, argv, *, cwd, env, timeout):
                from hakiosport.runner import Result

                return Result(argv=list(argv), returncode=0)

        with tempfile.TemporaryDirectory() as tmp:
            plan = self.make_plan()
            plan.kernel_src = Path(tmp)
            plan.steps = [
                build.BuildStep(
                    name="image",
                    argv=["python3", "tools/image.py", "build"],
                    cwd=tmp,
                )
            ]

            with self.assertRaisesRegex(
                BuildBlocked, "did not produce the expected boot image"
            ):
                build.build(SuccessfulHostRunner(), plan)


if __name__ == "__main__":
    unittest.main()
