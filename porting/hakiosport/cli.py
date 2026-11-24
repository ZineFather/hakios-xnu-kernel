#!/usr/bin/env python3
"""Command line front end for the RAM-only HakiOS porting tool.

The device is always a caller-supplied query: this module contains no phone name
of its own and passes ``--device`` / ``--codename`` straight to
:func:`hakiosport.devices.resolve`.  Only read-only device queries and
``fastboot boot <existing local file>`` can ever be reached from here, and that
boot path is gated inside :mod:`hakiosport.boot`.

Exit codes: 0 ok, 2 usage/missing tool, 3 unsupported hardware, 4 policy
violation, 5 build blocked, 6 boot failed, 7 audit failed.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from . import policy as _policy

if not hasattr(_policy, "FORBIDDEN_BOOTARGS"):
    # Compatibility shim for the current tree: audit.py imports this constant
    # from policy.py while its canonical definition lives in image.py. Supplying
    # it here keeps both modules importable without editing either of them.
    from .image import FORBIDDEN_BOOTARGS as _FORBIDDEN_BOOTARGS

    _policy.FORBIDDEN_BOOTARGS = _FORBIDDEN_BOOTARGS

from . import audit, boot as boot_mod, build as build_mod, devices, image as image_mod
from . import inspect as inspect_mod
from .adb import Adb
from .boot import Detection, RECOVERY_INSTRUCTIONS
from .devices import DeviceSpec, capability
from .errors import BuildBlocked, HakiosError, SafetyAuditFailed, UsageError
from .inspect import HardwareReport
from .report import render_boot_compatibility, render_hardware, write_json, write_text
from .runner import CommandRunner


class _Output:
    """Small stdout/stderr wrapper so ``--quiet`` cannot hide errors."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    def say(self, text: str = "") -> None:
        if not self.quiet:
            print(text)

    def warn(self, text: str) -> None:
        print("WARNING: " + text, file=sys.stderr)


@dataclass
class _Context:
    args: argparse.Namespace
    package_root: Path
    ports_dir: Path
    reports_dir: Path
    logs_dir: Path
    audit_path: Path
    spec: DeviceSpec
    runner: CommandRunner
    out: _Output


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #


def _add_common(parser: argparse.ArgumentParser, *, sub: bool = False) -> None:
    """Add the global options to a parser.

    Sub-parsers use ``SUPPRESS`` so an option given *before* the subcommand keeps
    its value while the same option given *after* it is still accepted.
    """

    value_default = argparse.SUPPRESS if sub else None
    flag_default = argparse.SUPPRESS if sub else False
    timeout_default = argparse.SUPPRESS if sub else 60.0

    parser.add_argument(
        "--device",
        default=value_default,
        metavar="NAME",
        help="device human name or model, e.g. 'Samsung Galaxy A52s 5G'",
    )
    parser.add_argument(
        "--codename",
        default=value_default,
        metavar="CODE",
        help="device codename from the registry or devices/, e.g. a52sxq",
    )
    parser.add_argument(
        "--serial",
        default=value_default,
        metavar="SERIAL",
        help="adb/fastboot serial to use when more than one device is attached",
    )
    parser.add_argument(
        "--kernel-src",
        default=value_default,
        metavar="DIR",
        help="HakiOS kernel checkout (used by build and verify-safety)",
    )
    parser.add_argument(
        "--ports-dir",
        default=value_default,
        metavar="DIR",
        help="directory holding device packages (default: <package>/devices)",
    )
    parser.add_argument(
        "--reports-dir",
        default=value_default,
        metavar="DIR",
        help="where reports are written (default: <package>/reports)",
    )
    parser.add_argument(
        "--audit-log",
        default=value_default,
        metavar="FILE",
        help="JSON Lines device-command log (default: <package>/logs/device-commands.jsonl)",
    )
    parser.add_argument(
        "--image",
        default=value_default,
        metavar="FILE",
        help="existing local boot image for the boot subcommand",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=timeout_default,
        metavar="SECONDS",
        help="host/device timeout and monitor duration (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=flag_default,
        help="show what would happen; spawn no tool and send no device command",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=flag_default,
        help="suppress ordinary output; errors are still printed",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=flag_default,
        help="echo commands inside the runner",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=flag_default,
        help="overwrite locally modified generated port files",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=flag_default,
        help="acknowledge an interactive boot confirmation prompt",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hakios_port.py",
        description=(
            "Inspect, generate, build, temporarily boot and audit a HakiOS port "
            "using only read-only device queries and a RAM-only boot."
        ),
        epilog=(
            "Nothing here writes to the phone: partition writes, erases and "
            "bootloader-state changes are refused by the command policy. "
            "A temporary boot starts an existing local file and a normal reboot "
            "returns the phone to stock Android. "
            "Exit codes: 0 ok, 2 usage/missing tool, 3 unsupported hardware, "
            "4 policy violation, 5 build blocked, 6 boot failed, 7 audit failed."
        ),
    )
    _add_common(parser)
    subs = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    subs.add_parser(
        "inspect",
        help="read hardware facts over adb and write an honest report",
        description=(
            "Read only what the phone reports over adb, plus fastboot variables "
            "when a bootloader is reachable. A missing device is recorded as such."
        ),
    )
    subs.add_parser(
        "port",
        help="generate or refresh the device package without clobbering edits",
        description="Create devices/<codename> from registry data and validate its structure.",
    )
    subs.add_parser(
        "build",
        help="plan and run the host-side loader, kernel and boot image build",
        description="Build on the host only; the no-persistent-log loader guard is verified.",
    )
    subs.add_parser(
        "boot",
        help="attempt one RAM-only boot of an existing local image",
        description=(
            "Gate on capability and identity before starting an image. Devices "
            "without a fastboot protocol are refused without a fallback."
        ),
    )
    subs.add_parser(
        "monitor",
        help="collect the temporary boot's RAM log onto the host",
        description="Poll read-only loader queries and pull staged logs to this computer.",
    )
    subs.add_parser(
        "reboot",
        help="return to stock Android and print manual recovery steps",
        description="Request an ordinary reboot when a device is reachable, otherwise print steps.",
    )
    subs.add_parser(
        "verify-safety",
        help="audit this workflow for persistent-write paths",
        description=(
            "Scan sources, verify the loader guard and binary when present, "
            "and re-check every recorded device command against the policy."
        ),
    )
    for sub in subs.choices.values():
        _add_common(sub, sub=True)
    return parser


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def _build_context(args: argparse.Namespace) -> _Context:
    package_root = Path(__file__).resolve().parent.parent
    ports_dir = Path(args.ports_dir).expanduser() if args.ports_dir else package_root / "devices"
    reports_dir = Path(args.reports_dir).expanduser() if args.reports_dir else package_root / "reports"
    logs_dir = package_root / "logs"
    audit_path = (
        Path(args.audit_log).expanduser() if args.audit_log else logs_dir / "device-commands.jsonl"
    )

    try:
        spec = devices.resolve(args.device or args.codename, ports_dir)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if args.device and args.codename:
        try:
            other = devices.resolve(args.codename, ports_dir)
        except ValueError as exc:
            raise UsageError(str(exc)) from exc
        if other.codename != spec.codename:
            raise UsageError(
                f"--device resolved to {spec.codename!r} but --codename resolved to "
                f"{other.codename!r}; pass only one of them"
            )

    out = _Output(args.quiet)
    runner = CommandRunner(
        audit_path=audit_path,
        dry_run=args.dry_run,
        verbose=bool(args.verbose and not args.quiet),
    )
    return _Context(
        args=args,
        package_root=package_root,
        ports_dir=ports_dir,
        reports_dir=reports_dir,
        logs_dir=logs_dir,
        audit_path=audit_path,
        spec=spec,
        runner=runner,
        out=out,
    )


def _announce(ctx: _Context) -> None:
    spec = ctx.spec
    ctx.out.say(f"Device: {spec.display_name} ({spec.codename})")
    if not spec.known:
        ctx.out.warn(
            f"{spec.display_name!r} is not in the device registry; "
            "identity must come from the phone itself"
        )
    ctx.out.say(
        f"Bootloader: {spec.bootloader_kind} "
        f"(documented fastboot boot: {spec.fastboot_boot})"
    )


def _maybe_image_info(path: Path):
    """Inspect a local image only when it exists; never invent details."""

    candidate = Path(path)
    if candidate.is_file():
        return image_mod.inspect_boot_image(candidate)
    return None


def _is_informational_issue(text: str) -> bool:
    lowered = text.lower()
    return "no loader" in lowered or "expected for an unported device" in lowered


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #


def _cmd_inspect(ctx: _Context) -> int:
    detection = boot_mod.detect(ctx.runner, ctx.spec, serial=ctx.args.serial)
    fastboot_vars = dict(detection.fastboot_vars)
    hardware: HardwareReport | None = None

    if detection.adb_available:
        try:
            hardware = inspect_mod.collect(
                Adb(ctx.runner),
                ctx.spec,
                serial=detection.adb_serial or ctx.args.serial,
                fastboot_vars=fastboot_vars,
                runner=ctx.runner,
            )
        except UsageError as exc:
            ctx.out.warn(f"the adb device could not be inspected: {exc}")

    if hardware is None:
        hardware = HardwareReport(spec=ctx.spec, fastboot_vars=fastboot_vars)
        if detection.adb_state == "tool-missing":
            hardware.add(
                "inspection.status",
                "no adb device was inspected: adb is not installed or not on PATH",
                "adb devices",
                "unknown",
            )
        else:
            hardware.add(
                "inspection.status",
                f"no adb device was inspected (adb state: {detection.adb_state})",
                "adb devices",
                "unknown",
            )
        hardware.add(
            "inspection.fastboot",
            (
                "fastboot variables were read from "
                f"{detection.fastboot_serial}"
                if fastboot_vars
                else f"no fastboot variables were read (state: {detection.fastboot_state})"
            ),
            "fastboot getvar all",
            "reported" if fastboot_vars else "unknown",
        )
        for note in detection.notes:
            hardware.add("inspection.note", note, "detection", "unknown")

    gate = capability(
        ctx.spec,
        fastboot_seen=detection.fastboot_available,
        fastboot_vars=fastboot_vars,
    )

    hardware_text = render_hardware(hardware)
    hardware_data = hardware.as_dict()

    # Generic names are stable for every device; the codename-prefixed copies are
    # the per-device artifacts requested by the porting workflow.  Both are
    # host-side writes and contain exactly the same observed data.
    hardware_md = write_text(ctx.reports_dir / "hardware.md", hardware_text)
    hardware_json = write_json(ctx.reports_dir / "hardware.json", hardware_data)
    device_md = write_text(
        ctx.reports_dir / f"{ctx.spec.codename}_hardware_report.md",
        hardware_text,
    )
    device_json = write_json(
        ctx.reports_dir / f"{ctx.spec.codename}_hardware_report.json",
        hardware_data,
    )
    compat_md = write_text(
        ctx.reports_dir / "boot-compatibility.md",
        render_boot_compatibility(
            ctx.spec,
            gate,
            detection=detection.as_dict(),
        ),
    )

    ctx.out.say(f"Device inspected: {'yes' if hardware.device_present else 'no'}")
    ctx.out.say(f"Boot allowed: {'yes' if gate.supported else 'no'} - {gate.reason}")
    ctx.out.say(f"Hardware report: {hardware_md}")
    ctx.out.say(f"Hardware JSON: {hardware_json}")
    ctx.out.say(f"Device hardware report: {device_md}")
    ctx.out.say(f"Device hardware JSON: {device_json}")
    ctx.out.say(f"Boot compatibility: {compat_md}")
    return 0


def _cmd_port(ctx: _Context) -> int:
    from . import portgen  # imported here so other subcommands do not depend on it

    result = portgen.generate(ctx.spec, ctx.ports_dir, force=ctx.args.force)
    informational: list[str] = []
    unexpected: list[str] = []
    for issue in result.issues:
        (informational if _is_informational_issue(issue) else unexpected).append(issue)

    payload = {
        "port": str(result.port),
        "created": result.created,
        "unchanged": result.unchanged,
        "skipped_modified": result.skipped_modified,
        "issues": result.issues,
        "informational_issues": informational,
        "unexpected_issues": unexpected,
        "status": portgen.status(ctx.spec, result.port),
    }
    report_path = write_json(ctx.reports_dir / "port-generation.json", payload)

    ctx.out.say(f"Port: {result.port}")
    ctx.out.say("Created: " + (", ".join(result.created) or "none"))
    ctx.out.say("Unchanged: " + (", ".join(result.unchanged) or "none"))
    ctx.out.say("Skipped (locally modified): " + (", ".join(result.skipped_modified) or "none"))
    for issue in informational:
        ctx.out.say(f"Note: {issue}")
    for issue in unexpected:
        ctx.out.warn(issue)
    ctx.out.say(f"Report: {report_path}")

    if unexpected:
        raise SafetyAuditFailed(
            "the generated device package has unexpected issues",
            detail="\n".join(unexpected),
        )
    return 0


def _cmd_build(ctx: _Context) -> int:
    plan_result = build_mod.plan(
        ctx.spec,
        kernel_src=ctx.args.kernel_src,
        ports_dir=ctx.ports_dir,
    )
    plan_path = write_json(ctx.reports_dir / "build-plan.json", plan_result.as_dict())
    report_path = ctx.reports_dir / "build-report.json"

    host = plan_result.host
    ctx.out.say(
        f"Host: {host.system} {host.release} {host.machine} "
        f"(supported for build: {'yes' if host.supported else 'no'})"
    )
    ctx.out.say(host.note or "No host note recorded.")
    ctx.out.say(f"Kernel checkout: {plan_result.kernel_src or 'not found'}")
    ctx.out.say(f"Plan: {plan_path}")
    ctx.out.say(f"Steps: {len(plan_result.steps)}")

    if plan_result.blocked:
        for blocker in plan_result.blockers:
            ctx.out.say(f"Blocker: {blocker}")
        if not ctx.args.dry_run:
            write_json(report_path, build_mod.BuildReport(plan=plan_result).as_dict())
            raise BuildBlocked(
                "the build cannot run on this host",
                detail="\n".join(f"- {item}" for item in plan_result.blockers),
            )
        ctx.out.say("Dry run: blocked steps are recorded but nothing is executed.")

    saved_blockers = list(plan_result.blockers)
    try:
        if ctx.args.dry_run:
            # A dry run must complete even on a host that cannot build. The real
            # blockers stay in the written plan and in this report.
            plan_result.blockers = []
        report = build_mod.build(ctx.runner, plan_result, dry_run=ctx.args.dry_run)
    except HakiosError:
        plan_result.blockers = saved_blockers
        write_json(report_path, build_mod.BuildReport(plan=plan_result).as_dict())
        raise
    finally:
        plan_result.blockers = saved_blockers

    write_json(report_path, report.as_dict())
    for item in report.results:
        state = "dry-run" if item.get("dry_run") else f"exit {item.get('returncode')}"
        ctx.out.say(f"  {item.get('name', 'step')}: {state}")
    if report.loader_check is None:
        reason = "dry run" if ctx.args.dry_run else "no loader step in this plan"
        ctx.out.say(f"Loader check: not performed ({reason})")
    else:
        ok, detail = report.loader_check
        ctx.out.say(f"Loader check: {'PASS' if ok else 'FAIL'} - {detail}")
    ctx.out.say(f"Build completed: {'yes' if report.completed else 'no'}")
    ctx.out.say(f"Build report: {report_path}")
    return 0


def _cmd_boot(ctx: _Context) -> int:
    spec = ctx.spec
    if spec.fastboot_boot is False:
        # No fastboot protocol means detection cannot help and must not be run.
        # The capability gate in boot.boot() refuses before any device command.
        detection = Detection(
            notes=[
                f"{spec.codename} uses the {spec.bootloader_kind} bootloader: "
                "read-only device probing was skipped"
            ]
        )
    else:
        detection = boot_mod.detect(ctx.runner, spec, serial=ctx.args.serial)

    gate = capability(
        spec,
        fastboot_seen=detection.fastboot_available,
        fastboot_vars=detection.fastboot_vars,
    )

    kernel_src = build_mod.find_kernel_source(ctx.args.kernel_src)
    if ctx.args.image:
        image_path = Path(ctx.args.image).expanduser()
    elif kernel_src is not None:
        image_path = build_mod.image_path(kernel_src, spec)
    else:
        image_path = ctx.package_root / "build" / "images" / spec.codename / "boot.img"

    compat_path = write_text(
        ctx.reports_dir / "boot-compatibility.md",
        render_boot_compatibility(
            spec,
            gate,
            detection=detection.as_dict(),
            image=_maybe_image_info(image_path),
        ),
    )
    result_path = ctx.reports_dir / "boot-result.json"

    ctx.out.say(f"Image: {image_path}")
    ctx.out.say(f"Boot allowed: {'yes' if gate.supported else 'no'} - {gate.reason}")
    ctx.out.say(f"Boot compatibility: {compat_path}")

    if gate.supported and not ctx.args.dry_run and not ctx.args.yes and sys.stdin.isatty():
        answer = input("Start this temporary image? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            raise UsageError("boot cancelled by the user; nothing was sent to the device")

    try:
        result = boot_mod.boot(
            ctx.runner,
            spec,
            image_path,
            serial=ctx.args.serial,
            detection=detection,
            log_dir=ctx.logs_dir,
            dry_run=ctx.args.dry_run,
            timeout=ctx.args.timeout,
        )
    except HakiosError as exc:
        write_json(
            result_path,
            {
                "spec": spec.as_dict(),
                "detection": detection.as_dict(),
                "capability": {
                    "supported": gate.supported,
                    "reason": gate.reason,
                    "evidence": gate.evidence,
                    "checks": dict(gate.checks),
                },
                "image_path": str(image_path),
                "error": type(exc).__name__,
                "message": exc.message,
                "detail": exc.detail,
                "started": False,
            },
        )
        ctx.out.say(f"Boot result: {result_path}")
        raise

    write_json(result_path, result.as_dict())
    ctx.out.say(f"Started: {'yes' if result.started else 'no'}")
    ctx.out.say(f"Boot log: {result.log_path or 'none'}")
    for note in result.notes:
        ctx.out.say(f"Note: {note}")
    ctx.out.say(f"Boot result: {result_path}")
    return 0


def _cmd_monitor(ctx: _Context) -> int:
    duration = 0.0 if ctx.args.dry_run else ctx.args.timeout
    if ctx.args.dry_run:
        ctx.out.say("Dry run: monitor duration shortened to zero; no polling is performed.")
    outcome = boot_mod.monitor(
        ctx.runner,
        serial=ctx.args.serial,
        duration=duration,
        log_dir=ctx.logs_dir,
    )
    result_path = write_json(ctx.reports_dir / "monitor-result.json", outcome)
    summary = outcome["summary"]
    ctx.out.say(f"Log: {outcome['log_path']}")
    ctx.out.say(
        f"Lines: {summary['lines']}, kernel started: {summary['kernel_started']}, "
        f"panic: {summary['panic']}, errors: {len(summary['errors'])}"
    )
    ctx.out.say(f"Polls: {outcome['polls']}, loader seen: {outcome['loader_seen']}")
    for note in outcome["notes"]:
        ctx.out.say(f"Note: {note}")
    ctx.out.say(f"Result: {result_path}")
    return 0


def _cmd_reboot(ctx: _Context) -> int:
    if ctx.runner.dry_run:
        text = "Dry run: no device command was sent.\n\n" + RECOVERY_INSTRUCTIONS
    else:
        text = boot_mod.reboot_to_android(ctx.runner, serial=ctx.args.serial)
        if RECOVERY_INSTRUCTIONS not in text:
            text += "\n\n" + RECOVERY_INSTRUCTIONS
    path = write_text(ctx.reports_dir / "recovery.txt", text.rstrip() + "\n")
    ctx.out.say(text)
    ctx.out.say(f"Recovery steps saved: {path}")
    return 0


def _cmd_verify_safety(ctx: _Context) -> int:
    kernel_src = build_mod.find_kernel_source(ctx.args.kernel_src)
    repos = [ctx.package_root]
    if kernel_src is not None and kernel_src.is_dir():
        repos.append(kernel_src)

    findings: list = []
    seen: set[tuple[str, int, str]] = set()
    for repo in repos:
        for finding in audit.scan_tree(repo):
            key = (finding.path, finding.line, finding.text)
            if key in seen:
                continue
            seen.add(key)
            findings.append(finding)

    summary = audit.summarize(findings)
    failures: list[str] = []

    patch_status = None
    patch_check = {"checked": False, "reason": "no kernel checkout found"}
    if kernel_src is not None and kernel_src.is_dir():
        patch_status = audit.verify_patch(kernel_src)
        patch_check = {
            "checked": True,
            "ok": patch_status[0],
            "detail": patch_status[1],
        }
        if not patch_status[0]:
            failures.append("loader source guard: " + patch_status[1])

    binary_status = None
    binary_check = {"checked": False, "reason": "no loader binary found; no build has happened"}
    if kernel_src is not None and kernel_src.is_dir():
        loader = build_mod.loader_path(kernel_src)
        if loader.is_file():
            binary_status = audit.verify_loader_binary(loader)
            binary_check = {
                "checked": True,
                "ok": binary_status[0],
                "detail": binary_status[1],
            }
            if not binary_status[0]:
                failures.append("loader binary: " + binary_status[1])

    log_ok, log_problems = audit.verify_command_log(ctx.audit_path)
    command_log_check = {"ok": log_ok, "problems": log_problems}
    if not log_ok:
        failures.append("device command log: " + "; ".join(log_problems))

    if summary["unmitigated_persistent"]:
        for item in summary["unmitigated"]:
            failures.append(
                f"{item['path']}:{item['line']} {item['rationale']} (no mitigation)"
            )

    md_path = write_text(
        ctx.reports_dir / "storage-audit.md",
        audit.render(findings, repos=repos, patch_status=patch_status, binary_status=binary_status),
    )
    json_path = write_json(
        ctx.reports_dir / "storage-audit.json",
        {
            "repos": [str(repo) for repo in repos],
            "summary": summary,
            "findings": [finding.as_dict() for finding in findings],
            "patch_check": patch_check,
            "binary_check": binary_check,
            "command_log_check": command_log_check,
            "failures": failures,
            "ok": not failures,
        },
    )

    counts = ", ".join(f"{key}={value}" for key, value in sorted(summary["counts"].items()))
    ctx.out.say(f"Findings: {len(findings)} ({counts or 'none'})")
    ctx.out.say(f"Unmitigated persistent writes: {summary['unmitigated_persistent']}")
    ctx.out.say("Checks: patch=" + (f"{'PASS' if patch_check.get('ok') else 'FAIL'}"
                                    if patch_check["checked"] else "not checked")
                + ", loader=" + (f"{'PASS' if binary_check.get('ok') else 'FAIL'}"
                                 if binary_check["checked"] else "not checked")
                + ", command log=" + ("PASS" if log_ok else "FAIL"))
    ctx.out.say(f"Audit: {'PASS' if not failures else 'FAIL'}")
    ctx.out.say(f"Markdown: {md_path}")
    ctx.out.say(f"JSON: {json_path}")

    if failures:
        raise SafetyAuditFailed("the storage-write audit failed", detail="\n".join(failures))
    return 0


_COMMANDS = {
    "inspect": _cmd_inspect,
    "port": _cmd_port,
    "build": _cmd_build,
    "boot": _cmd_boot,
    "monitor": _cmd_monitor,
    "reboot": _cmd_reboot,
    "verify-safety": _cmd_verify_safety,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run one subcommand, and map failures to exit codes."""

    try:
        args = _parser().parse_args(argv)
        ctx = _build_context(args)
        _announce(ctx)
        return _COMMANDS[args.command](ctx)
    except HakiosError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        if exc.detail:
            print(exc.detail, file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("ERROR: interrupted by user", file=sys.stderr)
        return 130
