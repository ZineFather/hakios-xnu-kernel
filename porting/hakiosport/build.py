"""Building the three things a temporary boot needs: the loader, the kernel, an image.

Nothing here touches a phone.  Every command runs on the host, in the kernel
checkout, and the result is a file on this computer.

The loader is the part that matters for the storage policy: upstream's loader
writes its log to a ``logdump`` partition after every run.  This module always
passes ``-DHAKIOS_NO_PERSISTENT_LOG=1`` and, after building, inspects the binary
for the partition name.  A loader that still carries it is not returned, used or
reported as built.

Failure modes are explicit:

* wrong host, missing toolchain, missing sources  -> :class:`BuildBlocked` (exit 5)
* a built loader still containing ``logdump``     -> :class:`SafetyAuditFailed` (exit 7)
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from . import audit, image
from .devices import DeviceSpec
from .errors import BuildBlocked, SafetyAuditFailed, UsageError
from .runner import CommandRunner, Result

#: The define that compiles the persistent log write out of the loader.
NO_PERSISTENT_LOG_FLAG = "-DHAKIOS_NO_PERSISTENT_LOG=1"

#: Tools the loader needs (clang + lld, exactly as build.config.loader says).
LOADER_TOOLS = ("clang", "lld-link", "python3")
#: Tools the kernel build needs, roughly: the kernel's own build.sh decides more.
KERNEL_TOOLS = ("make", "git", "python3")
#: The image step is the project's own tool.
IMAGE_TOOLS = ("python3",)

#: Where a kernel checkout usually is, when --kernel-src is not given.
DEFAULT_KERNEL_LOCATIONS = (
    "kernel-src",
    "../kernel-src",
    "hakios/kernel",
    "../hakios/kernel",
    "~/hakios/kernel",
    "~/src/hakios/kernel",
)


@dataclass
class HostInfo:
    system: str
    release: str
    machine: str
    distro_id: str = ""
    distro_like: str = ""
    distro_name: str = ""
    supported: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "system": self.system,
            "release": self.release,
            "machine": self.machine,
            "distro_id": self.distro_id,
            "distro_like": self.distro_like,
            "distro_name": self.distro_name,
            "supported_for_build": self.supported,
            "note": self.note,
        }


def detect_host() -> HostInfo:
    """Identify the host OS, including the Arch/CachyOS distinction.

    HakiOS's builds are ``bash`` scripts that use GNU make, clang targeting
    ``aarch64-unknown-windows`` and ``lld-link``.  They are developed on Linux and
    macOS.  A Windows host cannot run them natively; WSL is a Linux host and works.
    """

    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    info = HostInfo(system=system, release=release, machine=machine)

    os_release = Path("/etc/os-release")
    if os_release.is_file():
        values: dict[str, str] = {}
        try:
            for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"')
        except OSError:
            values = {}
        info.distro_id = values.get("ID", "")
        info.distro_like = values.get("ID_LIKE", "")
        info.distro_name = values.get("PRETTY_NAME", "") or values.get("NAME", "")

    if system == "Linux":
        info.supported = True
        families = {info.distro_id, *info.distro_like.split()}
        if "arch" in families or "cachyos" in families or info.distro_id == "cachyos":
            info.note = (
                "Arch-family host: the toolchain is in the official repositories "
                "(pacman -S clang lld make git python android-tools)."
            )
        else:
            info.note = "Linux host: install clang, lld, make, git, python3 and android-tools."
    elif system == "Darwin":
        info.supported = True
        info.note = "macOS host: clang and lld come with the Xcode command line tools."
    elif system == "Windows":
        info.supported = False
        info.note = (
            "Windows host: HakiOS builds are bash + GNU make + clang/lld-link and are "
            "not supported natively. Use WSL2 (Ubuntu or Arch) and run the tool there. "
            "The policy, inspection, audit and reporting parts of this tool do run here."
        )
    else:
        info.supported = False
        info.note = f"{system} is not a supported build host."

    return info


def find_kernel_source(explicit: str | None = None) -> Path | None:
    """Locate a HakiOS kernel checkout.

    Order: the explicit path, ``$HAKIOS_KERNEL``, then the conventional locations.
    A directory only counts when it has the two scripts a build uses.
    """

    def plausible(path: Path) -> bool:
        return (
            (path / "Makefile").is_file()
            and (path / "arch/arm64/boot/build.sh").is_file()
            and (path / "tools/image.py").is_file()
        )

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get("HAKIOS_KERNEL")
    if env:
        candidates.append(Path(env).expanduser())
    for value in DEFAULT_KERNEL_LOCATIONS:
        candidates.append(Path(value).expanduser())

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if plausible(resolved):
            return resolved
    return None


@dataclass
class BuildStep:
    name: str
    argv: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 3600.0
    note: str = ""
    produces: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "argv": self.argv,
            "cwd": self.cwd,
            "env": {k: v for k, v in self.env.items() if k in {"LOADER_CFLAGS"}},
            "note": self.note,
            "produces": self.produces,
        }


@dataclass
class BuildPlan:
    spec: DeviceSpec
    kernel_src: Path | None
    host: HostInfo
    steps: list[BuildStep] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    missing_tools: dict[str, str] = field(default_factory=dict)
    port_package: Path | None = None

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    def as_dict(self) -> dict:
        return {
            "device": self.spec.codename,
            "host": self.host.as_dict(),
            "kernel_src": str(self.kernel_src) if self.kernel_src else None,
            "port_package": str(self.port_package) if self.port_package else None,
            "blocked": self.blocked,
            "blockers": self.blockers,
            "missing_tools": self.missing_tools,
            "steps": [step.as_dict() for step in self.steps],
        }


def _tool_status(names: Sequence[str]) -> dict[str, str]:
    """Map each wanted tool to its path, or to an empty string when absent."""

    found: dict[str, str] = {}
    for name in names:
        path = shutil.which(name)
        if not path and name == "python3":
            # Some systems only have `python`; the HakiOS scripts call python3,
            # so this is reported rather than silently satisfied.
            path = ""
        found[name] = path or ""
    return found


def plan(
    spec: DeviceSpec,
    *,
    kernel_src: str | None = None,
    ports_dir: Path,
    defconfig: str = "phone_first",
    build_dir: str | None = None,
) -> BuildPlan:
    """Work out what a build would run, and everything that prevents it."""

    host = detect_host()
    resolved = find_kernel_source(kernel_src)
    result = BuildPlan(spec=spec, kernel_src=resolved, host=host)

    port = Path(ports_dir) / spec.codename
    result.port_package = port if (port / "board.dts").is_file() else None

    if not host.supported:
        result.blockers.append(host.note)

    if resolved is None:
        result.blockers.append(
            "no HakiOS kernel checkout found: pass --kernel-src DIR or set HAKIOS_KERNEL. "
            "The checkout needs Makefile, arch/arm64/boot/build.sh and tools/image.py "
            "(git clone -b common https://github.com/oosexgang/hakios-xnu-kernel)."
        )

    if result.port_package is None:
        result.blockers.append(
            f"no device package at {port}: run `hakios_port.py port` first, and make sure "
            "the package is imported into the kernel checkout with tools/device.py add"
        )

    tools = _tool_status((*LOADER_TOOLS, *KERNEL_TOOLS))
    missing = {name: path for name, path in tools.items() if not path}
    result.missing_tools = missing
    if missing and host.supported:
        result.blockers.append(
            "missing build tools: "
            + ", ".join(sorted(missing))
            + ". Arch/CachyOS: sudo pacman -S clang lld make git python python-android-tools"
        )

    if resolved is not None and resolved.is_dir() and result.port_package is not None:
        # Is the package actually inside the checkout the build will read?
        inside = resolved / "arch/arm64/boot/dts" / spec.codename / "board.dts"
        if not inside.is_file():
            result.blockers.append(
                f"the kernel checkout does not contain devices/{spec.codename}: run "
                f"`python3 tools/device.py add --from {port}` inside {resolved}"
            )

    # The steps are recorded even when a checkout is missing: a dry run should
    # still show the workflow a real build would follow.  They are never executed
    # while any blocker is present.
    cwd = str(resolved) if resolved is not None else "<kernel checkout>"
    base = resolved if resolved is not None else Path("<kernel checkout>")
    out = build_dir or str(base / "build" / "images" / spec.codename)
    result.steps.append(
        BuildStep(
            name="validate device packages",
            argv=[sys.executable, "tools/boards.py", "check"],
            cwd=cwd,
            timeout=300,
            note="HakiOS's own structural check of every device package",
            produces="a validated device table",
        )
    )
    result.steps.append(
        BuildStep(
            name="loader",
            argv=["/bin/bash", "arch/arm64/boot/build.sh"],
            cwd=cwd,
            env={"LOADER_CFLAGS": NO_PERSISTENT_LOG_FLAG},
            timeout=1800,
            note=(
                "freestanding AArch64 UEFI loader, built with the log-partition write "
                f"compiled out ({NO_PERSISTENT_LOG_FLAG})"
            ),
            produces="arch/arm64/boot/loader.efi",
        )
    )
    result.steps.append(
        BuildStep(
            name="kernel",
            argv=["make", "kernel"],
            cwd=cwd,
            timeout=7200,
            note="XNU for arm64, via kernel/build.sh",
            produces="the kernel under the checkout's build directory",
        )
    )
    result.steps.append(
        BuildStep(
            name="image",
            argv=[
                sys.executable,
                "tools/image.py",
                "build",
                "--board",
                spec.codename,
                "--defconfig",
                defconfig,
                "--out",
                out,
            ],
            cwd=cwd,
            timeout=1800,
            note=(
                "loader + kernel + boot arguments into an Android boot image for "
                "`fastboot boot` (this needs the phone's own uefi block and a UEFI "
                "build for it)"
            ),
            produces=f"{out}/boot.img",
        )
    )

    return result


def loader_path(kernel_src: Path) -> Path:
    return Path(kernel_src) / "arch/arm64/boot/loader.efi"


def image_path(kernel_src: Path, spec: DeviceSpec, build_dir: str | None = None) -> Path:
    base = Path(build_dir) if build_dir else Path(kernel_src) / "build" / "images" / spec.codename
    return base / "boot.img"


@dataclass
class BuildReport:
    plan: BuildPlan
    results: list[dict] = field(default_factory=list)
    loader_check: tuple[bool, str] | None = None
    image_info: dict | None = None
    completed: bool = False

    def as_dict(self) -> dict:
        return {
            "plan": self.plan.as_dict(),
            "results": self.results,
            "loader_check": (
                {"ok": self.loader_check[0], "detail": self.loader_check[1]}
                if self.loader_check
                else None
            ),
            "image": self.image_info,
            "completed": self.completed,
        }


def build(
    runner: CommandRunner,
    plan_result: BuildPlan,
    *,
    dry_run: bool = False,
    stop_at: str | None = None,
) -> BuildReport:
    """Run the plan.  Stops at the first failure; never continues past a bad loader."""

    report = BuildReport(plan=plan_result)

    if plan_result.blocked:
        raise BuildBlocked(
            "the build cannot run on this host",
            detail="\n".join(f"- {reason}" for reason in plan_result.blockers),
        )

    for step in plan_result.steps:
        if stop_at and step.name == stop_at:
            break
        if dry_run:
            report.results.append(
                {
                    "name": step.name,
                    "argv": step.argv,
                    "cwd": step.cwd,
                    "dry_run": True,
                    "returncode": 0,
                }
            )
            continue

        env = os.environ.copy()
        env.update(step.env)
        result = runner.host(
            step.argv,
            cwd=step.cwd,
            env=env,
            timeout=step.timeout,
        )
        record = {
            "name": step.name,
            "argv": step.argv,
            "cwd": step.cwd,
            "returncode": result.returncode,
            "duration_s": round(result.duration, 1),
            "tail": result.tail(30),
        }
        report.results.append(record)

        if not result.ok:
            if step.name == "loader":
                raise BuildBlocked(
                    "the loader build failed",
                    detail=result.tail(40),
                )
            if step.name == "kernel":
                raise BuildBlocked("the kernel build failed", detail=result.tail(40))
            raise BuildBlocked(f"the {step.name} step failed", detail=result.tail(40))

        # The whole point of the project: a loader that cannot write logdump.
        if step.name == "loader":
            path = loader_path(plan_result.kernel_src)  # type: ignore[arg-type]
            ok, detail = audit.verify_loader_binary(path)
            report.loader_check = (ok, detail)
            if not ok:
                raise SafetyAuditFailed(
                    "the built loader can still write the persistent log partition",
                    detail=(
                        detail
                        + "\n\nThe boot workflow stops here. Rebuild after checking that "
                        f"LOADER_CFLAGS={NO_PERSISTENT_LOG_FLAG} reached build.sh, and that "
                        "patches/0001-loader-no-persistent-log.patch is applied."
                    ),
                )

        if step.name == "image":
            target = image_path(plan_result.kernel_src, plan_result.spec, None)  # type: ignore[arg-type]
            if target.is_file():
                info = image.inspect_boot_image(target)
                report.image_info = info.as_dict()
                if not info.valid:
                    raise BuildBlocked(
                        "the built image failed validation",
                        detail="\n".join(info.reasons),
                    )

    report.completed = True
    return report
