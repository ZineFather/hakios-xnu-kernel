"""Process execution, with an audit trail and the policy gate wired in.

No part of this module ever uses ``shell=True``.  Device commands go through
:meth:`CommandRunner.adb` / :meth:`CommandRunner.fastboot`, which call the policy
first; a caller that tries to bypass it has to construct a raw ``subprocess`` call
itself, which the storage audit flags.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from . import policy
from .errors import PolicyViolation, UsageError


@dataclass
class Result:
    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    timed_out: bool = False
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Both streams: fastboot reports ``getvar`` answers on stderr."""

        return (self.stdout or "") + (self.stderr or "")

    def tail(self, lines: int = 20) -> str:
        text = self.output.strip().splitlines()
        return "\n".join(text[-lines:])


def find_tool(name: str, extra: Iterable[Path | str] = ()) -> str | None:
    """Locate an executable, including the usual Android SDK locations.

    Order: explicit extras, ``$PATH``, ``$ANDROID_HOME``/``$ANDROID_SDK_ROOT``
    platform-tools, then a few conventional install paths.  Returns ``None`` when
    the tool is genuinely absent; callers must say so rather than pretend.
    """

    candidates: list[Path] = [Path(p) for p in extra]
    exe = name + (".exe" if os.name == "nt" else "")
    for base in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")):
        if base:
            candidates.append(Path(base) / "platform-tools" / exe)
    home = Path.home()
    candidates.extend(
        [
            Path("/usr/bin") / name,
            Path("/usr/local/bin") / name,
            Path("/opt/android-sdk/platform-tools") / exe,
            home / "Android/Sdk/platform-tools" / exe,
            home / "android-sdk/platform-tools" / exe,
            Path("C:/platform-tools") / exe,
            Path("C:/adb") / exe,
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which(name)
    return found


class CommandRunner:
    """Runs host tools and device tools, recording every device command.

    ``audit_path`` is a JSON Lines file on the host.  It records the argv, exit
    code and duration of each *device* command, which is what a later review needs
    to prove that only read-only queries and ``fastboot boot`` were issued.
    """

    def __init__(
        self,
        *,
        audit_path: Path | None = None,
        timeout: float = 60.0,
        dry_run: bool = False,
        verbose: bool = False,
        stream: object | None = None,
    ) -> None:
        self.audit_path = Path(audit_path) if audit_path else None
        self.timeout = timeout
        self.dry_run = dry_run
        self.verbose = verbose
        self.stream = stream
        self.records: list[dict] = []
        self.adb_path = find_tool("adb")
        self.fastboot_path = find_tool("fastboot")
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    # -- internals -------------------------------------------------------- #

    def _say(self, text: str) -> None:
        if self.stream is not None and hasattr(self.stream, "write"):
            self.stream.write(text + "\n")
        elif self.verbose:
            print(text)

    def _record(self, argv: Sequence[str], result: Result, kind: str) -> None:
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kind": kind,
            "argv": list(argv),
            "returncode": result.returncode,
            "duration_s": round(result.duration, 3),
            "timed_out": result.timed_out,
            "dry_run": result.dry_run,
            "stdout_bytes": len(result.stdout.encode("utf-8", "replace")),
            "stderr_head": result.stderr[:400],
        }
        self.records.append(record)
        if self.audit_path:
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _run(
        self,
        argv: Sequence[str],
        *,
        kind: str,
        timeout: float | None = None,
        input_text: str | None = None,
        check: bool = False,
    ) -> Result:
        argv = [str(a) for a in argv]
        if self.verbose:
            self._say("$ " + " ".join(argv))

        if self.dry_run:
            result = Result(argv=list(argv), returncode=0, dry_run=True, duration=0.0)
            self._record(argv, result, kind)
            return result

        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout if timeout is not None else self.timeout,
                input=input_text,
                shell=False,
            )
            result = Result(
                argv=list(argv),
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                duration=time.monotonic() - started,
            )
        except FileNotFoundError as exc:
            raise UsageError(f"executable not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            result = Result(
                argv=list(argv),
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                duration=time.monotonic() - started,
                timed_out=True,
            )

        self._record(argv, result, kind)
        if check and not result.ok:
            raise UsageError(
                f"command failed ({result.returncode}): {' '.join(argv)}",
                detail=result.tail(),
            )
        return result

    # -- device tools ----------------------------------------------------- #

    def _device_tool(self, name: str) -> str:
        path = self.adb_path if name == "adb" else self.fastboot_path
        if not path:
            raise UsageError(
                f"{name} is not installed or not on PATH. "
                "Arch/CachyOS: sudo pacman -S android-tools. "
                "Windows: install Android platform-tools and add them to PATH."
            )
        return path

    def adb(self, args: Sequence[str], *, serial: str | None = None, timeout: float | None = None) -> Result:
        checked = policy.check_adb(args)
        argv = [self._device_tool("adb")]
        if serial:
            argv += ["-s", serial]
        argv += checked
        return self._run(argv, kind="adb", timeout=timeout)

    def fastboot(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
        timeout: float | None = None,
    ) -> Result:
        checked = policy.check_fastboot(args)
        argv = [self._device_tool("fastboot")]
        if serial:
            argv += ["-s", serial]
        argv += checked
        return self._run(argv, kind="fastboot", timeout=timeout)

    # -- host tools ------------------------------------------------------- #

    def host(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        check: bool = False,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        """Run a host-side tool (make, git, sha256sum...).  Not device-facing."""

        argv = [str(a) for a in argv]
        if self.dry_run:
            result = Result(argv=argv, returncode=0, dry_run=True)
            self._record(argv, result, "host")
            return result
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout if timeout is not None else self.timeout,
                shell=False,
                cwd=str(cwd) if cwd else None,
                env=dict(env) if env is not None else None,
            )
            result = Result(
                argv=argv,
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                duration=time.monotonic() - started,
            )
        except FileNotFoundError as exc:
            raise UsageError(f"host tool not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            result = Result(
                argv=argv,
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                duration=time.monotonic() - started,
                timed_out=True,
            )
        self._record(argv, result, "host")
        if check and not result.ok:
            raise UsageError(
                f"command failed ({result.returncode}): {' '.join(argv)}",
                detail=result.tail(),
            )
        return result
