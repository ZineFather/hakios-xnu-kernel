"""Temporary-boot workflow: detect, gate, inspect, then (only if allowed) boot.

This module is deliberately the *only* place that starts an image.  Every device
command is issued through :class:`hakiosport.runner.CommandRunner` via the small
clients in :mod:`hakiosport.adb` and :mod:`hakiosport.fastboot`; no ``subprocess``
call is constructed here.  Logs are collected and stored on the host only.

The safety order is part of the contract: capability is checked before identity,
identity before image inspection, and image inspection before any boot command.
A device with no fastboot protocol (such as a52sxq) is refused at the gate, so no
``fastboot boot`` argv is ever built for it, let alone executed.
"""

from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path

from .adb import Adb
from .devices import DeviceSpec, capability, verify_identity
from .errors import BootFailed, PolicyViolation, UnsupportedHardware, UsageError
from .fastboot import Fastboot
from .image import forbidden_args, inspect_boot_image
from .report import write_text
from .runner import CommandRunner


#: Safe manual steps shown when no device is connected (and as a coda to success).
#: The wording matters: it must never suggest Odin or any persistent write.
RECOVERY_INSTRUCTIONS = """Return to stock Android without changing storage:

1. If the phone is running the test image or is in a bootloader menu, hold Power \
for 10-15 seconds until it restarts, or choose the stock bootloader's normal boot \
/ "Restart bootloader" option.
2. If it is in Samsung Download (Odin) mode, do not connect Odin: leave Download \
mode with the normal boot / restart option, or hold Power until the phone restarts.
3. Let the stock bootloader start Android normally; nothing needs to be re-flashed.
4. In short: do not flash anything; a normal reboot preserves the original Android installation.

This tool never unlocks the bootloader, never flashes or erases partitions, never \
changes active slots, and never writes to the phone's storage. If the phone does \
not come back, stop and use the stock bootloader or recovery menu rather than \
substituting an Odin flash for a reboot."""


def _safe_name(value: str) -> str:
    """Make a string safe to use as one filename component on any host OS."""

    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._")
    return cleaned or "unknown"


def _note_error(notes: list[str], label: str, exc: BaseException) -> None:
    """Record a caught error without turning detection/monitoring into a crash."""

    notes.append(f"{label}: {exc}")
    detail = getattr(exc, "detail", None)
    if detail:
        notes.append("  " + str(detail).strip().replace("\n", " | "))


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #


@dataclass
class Detection:
    """What read-only discovery actually observed, never what was assumed.

    ``adb_available`` / ``fastboot_available`` mean a *device* was reachable over
    that transport (not merely that the host executable exists).  Tool absence is
    reported separately through the ``*_state`` fields.
    """

    adb_available: bool = False
    adb_state: str = "absent"  # device | unauthorized | offline | absent | tool-missing
    adb_serial: str = ""
    adb_identity: dict = field(default_factory=dict)
    fastboot_available: bool = False
    fastboot_state: str = "absent"  # device | absent | tool-missing
    fastboot_serial: str = ""
    fastboot_vars: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """JSON-friendly view used by reports and by :class:`BootResult`."""

        return {
            "adb_available": self.adb_available,
            "adb_state": self.adb_state,
            "adb_serial": self.adb_serial,
            "adb_identity": dict(self.adb_identity),
            "fastboot_available": self.fastboot_available,
            "fastboot_state": self.fastboot_state,
            "fastboot_serial": self.fastboot_serial,
            "fastboot_vars": dict(self.fastboot_vars),
            "notes": list(self.notes),
        }


def detect(runner: CommandRunner, spec: DeviceSpec, *, serial: str | None = None) -> Detection:
    """Probe both transports with read-only commands only.

    ``adb devices -l`` and ``adb shell getprop`` are used when an Android device is
    ready; ``fastboot devices`` and ``fastboot getvar all`` are used when a loader
    is visible.  A missing executable, missing device or failed query becomes a
    note and a state string -- detection always returns, even on a bare host.
    No write command is ever issued here.
    """

    detection = Detection()
    notes = detection.notes

    # -- ADB --------------------------------------------------------------- #
    if not getattr(runner, "adb_path", None):
        detection.adb_state = "tool-missing"
        notes.append("adb is not installed or not on PATH; no Android identity was read")
    else:
        devices: list = []
        try:
            devices = Adb(runner).devices()
        except UsageError as exc:
            _note_error(notes, "adb devices could not be queried", exc)

        matches = [d for d in devices if not serial or d.serial == serial]
        if serial and not matches:
            notes.append(f"no adb device with serial {serial!r} was listed")

        ready = [d for d in matches if d.ready]
        if len(ready) > 1 and not serial:
            detection.adb_state = "device"
            notes.append(
                "more than one adb device is ready ("
                + ", ".join(d.serial for d in ready)
                + "); pass --serial before trusting an identity check"
            )
        elif ready:
            chosen = ready[0]
            detection.adb_available = True
            detection.adb_state = "device"
            detection.adb_serial = chosen.serial
            try:
                detection.adb_identity = dict(Adb(runner).getprop(serial=chosen.serial))
            except UsageError as exc:
                _note_error(notes, "adb shell getprop could not be read", exc)
        elif matches:
            detection.adb_state = matches[0].state or "offline"
            detection.adb_serial = matches[0].serial
            notes.append(
                f"adb device {matches[0].serial} is {detection.adb_state}, not 'device'; "
                "identity was not read"
            )
        else:
            detection.adb_state = "absent"

    # -- fastboot ---------------------------------------------------------- #
    if not getattr(runner, "fastboot_path", None):
        detection.fastboot_state = "tool-missing"
        notes.append("fastboot is not installed or not on PATH; no bootloader variables were read")
    else:
        serials: list[str] = []
        try:
            serials = Fastboot(runner).devices()
        except UsageError as exc:
            _note_error(notes, "fastboot devices could not be queried", exc)

        if serial and serial not in serials:
            notes.append(f"no fastboot device with serial {serial!r} was listed")
        if len(serials) > 1 and not serial:
            notes.append(
                "more than one fastboot device is connected ("
                + ", ".join(serials)
                + "); pass --serial before a boot can be attributed safely"
            )

        chosen: str | None = None
        if serial:
            if serial in serials:
                chosen = serial
        elif len(serials) == 1:
            chosen = serials[0]

        if chosen:
            detection.fastboot_available = True
            detection.fastboot_state = "device"
            detection.fastboot_serial = chosen
            try:
                detection.fastboot_vars = dict(Fastboot(runner).getvar_all(serial=chosen))
            except UsageError as exc:
                _note_error(notes, "fastboot getvar all could not be read", exc)
        elif serials:
            detection.fastboot_state = "device"
            notes.append("a fastboot device is present but was not selected; variables were not read")
        else:
            detection.fastboot_state = "absent"

    if spec.fastboot_boot is False:
        alternate_path_note = (
            f"; the alternative path ({spec.alternate_boot_path}) writes persistent "
            "storage and is blocked"
            if (
                spec.alternate_boot_path
                and spec.alternate_boot_path_writes_persistent_storage
            )
            else ""
        )
        notes.append(
            f"{spec.codename} uses the {spec.bootloader_kind} bootloader, which does not "
            "implement fastboot; a normal reboot preserves the stock installation"
            + alternate_path_note
        )

    # ``spec`` is intentionally available here for the note above; nothing about
    # the device's capability is decided in detection (that is capability()'s job).
    return detection


# --------------------------------------------------------------------------- #
# boot
# --------------------------------------------------------------------------- #


@dataclass
class BootResult:
    """The full, reportable outcome of a boot attempt (dry runs included)."""

    spec: DeviceSpec
    detection: Detection
    image_path: str
    image: dict = field(default_factory=dict)  # BootImageInfo.as_dict()
    cap: dict = field(default_factory=dict)  # capability checks/reason
    started: bool = False
    command: list[str] = field(default_factory=list)
    log_path: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """JSON-friendly view; the spec is expanded so reports need no extra step."""

        return {
            "spec": self.spec.as_dict(),
            "detection": self.detection.as_dict(),
            "image_path": self.image_path,
            "image": dict(self.image),
            "cap": dict(self.cap),
            "started": self.started,
            "command": list(self.command),
            "log_path": self.log_path,
            "notes": list(self.notes),
        }


def _boot_argv(runner: CommandRunner, image: Path, serial: str | None) -> list[str]:
    """Build the argv *for reporting only*; execution goes through Fastboot.boot.

    Keeping this separate makes dry runs show exactly what would be sent, while
    never providing a shortcut that could spawn the command directly.
    """

    tool = getattr(runner, "fastboot_path", None) or "fastboot"
    argv = [str(tool)]
    if serial:
        argv += ["-s", serial]
    return argv + ["boot", str(image)]


def _write_boot_log(
    log_dir: Path,
    spec: DeviceSpec,
    detection: Detection,
    *,
    image: dict,
    cap: dict,
    command: list[str],
    outcome: str,
    started: bool,
    notes: list[str],
) -> str:
    """Write the attempt record on the host; a write failure never hides the boot."""

    path = Path(log_dir) / f"{_safe_name(spec.codename)}-boot.log"
    lines = [
        f"# Temporary boot attempt - {spec.display_name} ({spec.codename})",
        f"time: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"outcome: {outcome}",
        f"started: {started}",
        f"command: {shlex.join(command) if command else '(none - refused before boot)'}",
        f"adb_state: {detection.adb_state} (available={detection.adb_available}, serial={detection.adb_serial or '-'})",
        f"fastboot_state: {detection.fastboot_state} (available={detection.fastboot_available}, serial={detection.fastboot_serial or '-'})",
        f"capability_supported: {cap.get('supported')}",
        f"capability_reason: {cap.get('reason', '')}",
        f"image: {image.get('path', '')}",
        f"image_sha256: {image.get('sha256', '')}",
        f"image_valid: {image.get('valid')}",
        "No flashing, erase, format, unlock, slot change or device-side log write was performed.",
        "",
        "Notes:",
    ]
    lines += [f"- {note}" for note in notes] or ["- none"]
    try:
        write_text(path, "\n".join(lines) + "\n")
    except OSError as exc:  # pragma: no cover - depends on host permissions
        notes.append(f"could not write boot log {path}: {exc}")
    return str(path)


def boot(
    runner: CommandRunner,
    spec: DeviceSpec,
    image_path: Path,
    *,
    serial: str | None = None,
    detection: Detection | None = None,
    log_dir: Path | None = None,
    dry_run: bool = False,
    timeout: float = 180.0,
) -> BootResult:
    """Attempt a RAM-only boot, refusing early for any unsafe precondition.

    Order (do not reorder): detect -> capability gate -> identity -> image safety
    -> optional dry run -> ``Fastboot.boot`` -> host-side log.  For devices such as
    a52sxq the capability gate raises :class:`UnsupportedHardware` before any boot
    argv is executed; no flashing or Odin path exists as a fallback.
    """

    # 1. Detection (a supplied detection is trusted as an observation snapshot).
    found = detection if detection is not None else detect(runner, spec, serial=serial)
    notes = list(found.notes)

    # 2. Capability, from the registry and what detection actually saw.
    gate = capability(
        spec,
        fastboot_seen=found.fastboot_available,
        fastboot_vars=found.fastboot_vars,
    )
    cap = {
        "supported": gate.supported,
        "reason": gate.reason,
        "evidence": gate.evidence,
        "checks": dict(gate.checks),
    }

    # 3. The hard blocker: no fastboot protocol means no boot command at all.
    if not gate.supported:
        raise UnsupportedHardware(
            gate.reason,
            detail=gate.evidence
            + "\n\nThis tool will not substitute flashing or Odin."
            + (
                f" The alternate route ({spec.alternate_boot_path}) writes persistent "
                "storage and is forbidden."
                if (
                    spec.alternate_boot_path
                    and spec.alternate_boot_path_writes_persistent_storage
                )
                else ""
            ),
        )

    # 4. Never boot another phone's image just because the codename matched.
    if found.adb_identity:
        identity_ok, reasons = verify_identity(spec, found.adb_identity)
        if not identity_ok:
            raise UnsupportedHardware(
                f"the connected phone does not match {spec.display_name} ({spec.codename})",
                detail="\n".join(reasons) + "\n\nRefusing to boot another device's image.",
            )

    # 5. The image must be a real file whose command line cannot enable writes.
    path = Path(image_path)
    if not path.is_file():
        raise UsageError(f"boot image does not exist or is not a file: {path}")
    info = inspect_boot_image(path)
    image = info.as_dict()
    bad_args = list(dict.fromkeys(forbidden_args(info.payload_cmdline) + forbidden_args(info.cmdline)))
    if not info.valid or bad_args:
        reasons = list(info.reasons)
        reasons += [f"forbidden boot argument in image: {arg}" for arg in bad_args]
        raise PolicyViolation(
            "refusing to boot an invalid or write-enabling image",
            detail="\n".join(reasons) or "image inspection found no usable boot image",
        )

    directory = Path(log_dir) if log_dir is not None else Path("reports")

    # 6. Dry run: report the exact argv, but do not send it to the device.
    if dry_run:
        argv = _boot_argv(runner, path, serial)
        notes.append("dry run: no device command was sent")
        notes.append("would execute: " + shlex.join(argv))
        result = BootResult(
            spec=spec,
            detection=found,
            image_path=str(path),
            image=image,
            cap=cap,
            started=False,
            command=argv,
            log_path="",
            notes=notes,
        )
        result.log_path = _write_boot_log(
            directory,
            spec,
            found,
            image=image,
            cap=cap,
            command=argv,
            outcome="dry run (nothing sent to the device)",
            started=False,
            notes=notes,
        )
        return result

    # 7. The one permitted device-side start, via the policy-checked client.
    outcome = Fastboot(runner).boot(path, serial=serial, timeout=timeout)
    command = list(outcome.argv)
    started = outcome.ok and not getattr(outcome, "dry_run", False)
    if not started:
        tail = outcome.tail(20) or "fastboot boot returned no output"
        notes.append("fastboot boot did not start the image: " + tail.replace("\n", " | "))
        _write_boot_log(
            directory,
            spec,
            found,
            image=image,
            cap=cap,
            command=command,
            outcome="failed",
            started=False,
            notes=notes,
        )
        raise BootFailed(
            "fastboot boot failed",
            detail=tail + "\n\nNo partition was written; the phone was not modified.",
        )

    notes.append("temporary boot started; no partition was written")
    if getattr(outcome, "dry_run", False):
        notes.append("the runner itself is in dry-run mode: no process was spawned")

    # 8. Host-side record only.
    result = BootResult(
        spec=spec,
        detection=found,
        image_path=str(path),
        image=image,
        cap=cap,
        started=started,
        command=command,
        log_path="",
        notes=notes,
    )
    result.log_path = _write_boot_log(
        directory,
        spec,
        found,
        image=image,
        cap=cap,
        command=command,
        outcome="started",
        started=started,
        notes=notes,
    )
    return result


# --------------------------------------------------------------------------- #
# log summarising and monitoring
# --------------------------------------------------------------------------- #

_PANIC_MARKERS = ("panic(cpu", "kernel panic", "debugger called: <panic>")
_START_MARKER = "darwin kernel version"
_RETURN_MARKER = "kernel returned: log at"
_REFUSAL_MARKERS = ("not written", "refused", "no persistent log")
_FAILURE_RE = re.compile(r"\b(?:failed|stopped|timed out)\b", re.IGNORECASE)


def _unique(lines):
    """Keep matching lines in order, without duplicates."""

    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            kept.append(line)
    return kept


def summarize_log(text: str) -> dict:
    """Summarise a RAM log.  Pure function; no device or host I/O.

    Refusals to write are *good* news for this tool and are reported separately
    from errors.  Only unambiguous failure phrases count as errors, so an
    innocuous "error" in a path name does not look like a boot failure.
    """

    lines = [line.strip() for line in (text or "").splitlines()]
    lowered = [line.lower() for line in lines]

    panic_line = next(
        (line for line, low in zip(lines, lowered) if any(marker in low for marker in _PANIC_MARKERS)),
        "",
    )
    kernel_started = any(_START_MARKER in low for low in lowered)
    kernel_returned = any(_RETURN_MARKER in low for low in lowered)
    write_refusals = _unique(
        line for line, low in zip(lines, lowered) if line and any(m in low for m in _REFUSAL_MARKERS)
    )
    errors = _unique(line for line in lines if line and _FAILURE_RE.search(line))

    return {
        "lines": len(lines),
        "panic": bool(panic_line),
        "panic_line": panic_line,
        "kernel_started": kernel_started,
        "kernel_returned": kernel_returned,
        "errors": errors,
        "write_refusals": write_refusals,
    }


def _loader_codename(fastboot: Fastboot, serial: str | None, notes: list[str], log_file: Path | None) -> str:
    """Best-effort name for the monitor log; 'unknown' is allowed, a guess is not."""

    runner = getattr(fastboot, "runner", None)
    if not getattr(runner, "fastboot_path", None):
        notes.append("fastboot is not installed or not on PATH; the log name is best-effort")
    else:
        try:
            product = fastboot.getvar("product", serial=serial)
        except UsageError as exc:
            _note_error(notes, "fastboot getvar product", exc)
            product = None
        if product and product.lower() not in {"unknown", "(null)"}:
            return _safe_name(product)

    if log_file:
        stem = Path(log_file).stem
        for suffix in ("-boot", "-monitor", "-staged"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        if stem:
            return _safe_name(stem)
    return "unknown"


def monitor(
    runner: CommandRunner,
    *,
    serial: str | None = None,
    duration: float = 120.0,
    poll: float = 5.0,
    log_dir: Path | None = None,
    log_file: Path | None = None,
) -> dict:
    """Collect boot logs on the host while a temporary boot runs.

    Each poll repeats the read-only ``fastboot devices`` query.  When the loader
    reappears, ``fastboot get_staged <host file>`` pulls its RAM log device -> host.
    An already-existing local log can be included too.  Polling stops early on a
    kernel return-to-loader line or a panic.  No write command is issued.
    """

    notes: list[str] = []
    segments: list[str] = []
    directory = Path(log_dir) if log_dir is not None else Path("reports")
    fastboot = Fastboot(runner)
    codename = _loader_codename(fastboot, serial, notes, log_file)

    if log_file:
        local = Path(log_file)
        if local.is_file():
            try:
                text = local.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                notes.append(f"could not read local log {local}: {exc}")
            else:
                segments.append(f"# local log: {local}\n{text}")
                if local.stem.startswith(_safe_name(codename)):
                    notes.append("local log was included verbatim; it was not modified")
        else:
            notes.append(f"local log file does not exist: {local}")

    loader_seen = False
    staged_ok = False
    polls = 0
    stop_reason = ""
    started_at = time.monotonic()
    tool_missing = not getattr(runner, "fastboot_path", None)
    if tool_missing:
        notes.append("fastboot is not installed or not on PATH; no loader polling was possible")

    while not tool_missing:
        polls += 1
        try:
            serials = fastboot.devices()
        except UsageError as exc:
            _note_error(notes, "fastboot devices could not be queried", exc)
            break

        chosen: str | None = None
        if serial:
            if serial in serials:
                chosen = serial
            elif serials:
                notes.append(f"serial {serial!r} is not in fastboot devices; waiting for it")
        elif len(serials) == 1:
            chosen = serials[0]
        elif len(serials) > 1:
            notes.append("multiple fastboot devices; pass --serial to pull a staged log")

        if chosen:
            newly_seen = not loader_seen
            loader_seen = True
            if newly_seen or not staged_ok:
                staged_path = directory / f"{codename}-staged-{polls}.txt"
                try:
                    staged = fastboot.get_staged(staged_path, serial=chosen, timeout=120)
                except UsageError as exc:
                    _note_error(notes, "fastboot get_staged failed", exc)
                else:
                    if staged.ok and staged_path.is_file():
                        try:
                            text = staged_path.read_text(encoding="utf-8", errors="replace")
                        except OSError as exc:
                            notes.append(f"could not read staged log {staged_path}: {exc}")
                        else:
                            if text.strip():
                                segments.append(f"# staged RAM log (poll {polls}, {chosen})\n{text}")
                                staged_ok = True
                            else:
                                notes.append(f"staged log from {chosen} was empty")
                    else:
                        notes.append(
                            f"no staged log from {chosen}: " + (staged.tail(10) or "no output")
                        )

        summary = summarize_log("\n\n".join(segments))
        if summary["kernel_returned"]:
            stop_reason = "kernel returned to the loader"
            break
        if summary["panic"]:
            stop_reason = "kernel panic detected"
            break

        elapsed = time.monotonic() - started_at
        if elapsed >= max(0.0, duration):
            break
        delay = min(max(0.0, poll), max(0.0, duration) - elapsed)
        if delay > 0:
            time.sleep(delay)

    combined = "\n\n".join(segments)
    if stop_reason:
        notes.append("monitor stopped early: " + stop_reason)
    if not segments:
        notes.append("no boot log was collected")

    path = directory / f"{codename}-monitor.log"
    try:
        write_text(path, combined + ("\n" if combined else ""))
    except OSError as exc:  # pragma: no cover - depends on host permissions
        notes.append(f"could not write monitor log {path}: {exc}")

    return {
        "log_path": str(path),
        "summary": summarize_log(combined),
        "polls": polls,
        "loader_seen": loader_seen,
        "notes": notes,
    }


# --------------------------------------------------------------------------- #
# returning to stock Android
# --------------------------------------------------------------------------- #


def reboot_to_android(runner: CommandRunner, *, serial: str | None = None, via: str = "auto") -> str:
    """Return human-readable steps for going back to stock Android.

    With ``via='auto'`` an ordinary ``adb reboot`` or ``fastboot reboot`` is sent
    when a device is actually present; both are policy-allowed and neither changes
    partitions, slots or the unlock state.  If nothing is connected (or the tools
    are missing) the manual steps are returned instead, without raising.
    """

    mode = str(via or "auto").lower()
    if mode not in {"auto", "adb", "fastboot", "manual"}:
        return (
            RECOVERY_INSTRUCTIONS
            + f"\n\nUnknown reboot method {via!r}; no command was sent."
        )
    if mode == "manual":
        return RECOVERY_INSTRUCTIONS

    problems: list[str] = []

    if mode in {"auto", "adb"}:
        if not getattr(runner, "adb_path", None):
            problems.append("adb: not installed or not on PATH")
        else:
            try:
                ready = [
                    d for d in Adb(runner).devices()
                    if d.ready and (not serial or d.serial == serial)
                ]
            except UsageError as exc:
                problems.append(f"adb: {exc}")
            else:
                if ready:
                    target = ready[0].serial
                    try:
                        result = Adb(runner).reboot(serial=target)
                    except UsageError as exc:
                        problems.append(f"adb reboot: {exc}")
                    else:
                        if result.ok:
                            return (
                                "An ordinary Android reboot was requested over adb; no partitions, "
                                "slots or lock state were changed.\n\n" + RECOVERY_INSTRUCTIONS
                            )
                        problems.append("adb reboot: " + (result.tail(10) or "no output"))
                else:
                    problems.append("adb: no ready Android device")

    if mode in {"auto", "fastboot"}:
        if not getattr(runner, "fastboot_path", None):
            problems.append("fastboot: not installed or not on PATH")
        else:
            try:
                serials = Fastboot(runner).devices()
            except UsageError as exc:
                problems.append(f"fastboot: {exc}")
            else:
                chosen = (
                    serial if serial in serials
                    else (serials[0] if serials and not serial else None)
                )
                if chosen:
                    try:
                        result = Fastboot(runner).reboot(serial=chosen)
                    except UsageError as exc:
                        problems.append(f"fastboot reboot: {exc}")
                    else:
                        if result.ok:
                            return (
                                "A normal fastboot reboot was requested; no partitions, slots or "
                                "lock state were changed.\n\n" + RECOVERY_INSTRUCTIONS
                            )
                        problems.append("fastboot reboot: " + (result.tail(10) or "no output"))
                else:
                    problems.append("fastboot: no device in fastboot mode")

    return (
        RECOVERY_INSTRUCTIONS
        + "\n\nNo device command was sent."
        + ("\nDetails: " + "; ".join(problems) if problems else "")
    )
