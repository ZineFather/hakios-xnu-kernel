"""Fastboot client: discovery, read-only variables, and the one permitted boot.

``boot()`` is the only method that can start an image, and it goes through
:func:`hakiosport.policy.check_fastboot`, which accepts exactly one existing local
file.  There is deliberately no ``flash``, ``erase``, ``format`` or ``set_active``
method.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import UsageError
from .runner import CommandRunner, Result


@dataclass
class FastbootDevice:
    serial: str
    variables: dict[str, str]


_VAR_LINE = re.compile(r"^(?:\(bootloader\)\s*)?(?P<key>[A-Za-z0-9_.:/-]+)\s*:\s*(?P<value>.*)$")


class Fastboot:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    # -- discovery -------------------------------------------------------- #

    def devices(self) -> list[str]:
        result = self.runner.fastboot(["devices"], timeout=20)
        if not result.ok:
            return []
        serials: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            serials.append(line.split()[0])
        return serials

    def single(self, serial: str | None = None) -> FastbootDevice:
        serials = self.devices()
        if not serials:
            raise UsageError(
                "no device in fastboot mode. On this phone the bootloader may not "
                "expose a fastboot interface at all; see the boot-compatibility report."
            )
        if serial:
            if serial not in serials:
                raise UsageError(f"no fastboot device with serial {serial!r}")
            chosen = serial
        elif len(serials) == 1:
            chosen = serials[0]
        else:
            raise UsageError(
                "more than one fastboot device is connected; pass --serial "
                + ", ".join(serials)
            )
        return FastbootDevice(serial=chosen, variables=self.getvar_all(chosen))

    # -- reads ------------------------------------------------------------ #

    def getvar(self, name: str, serial: str | None = None) -> str | None:
        result = self.runner.fastboot(["getvar", name], serial=serial, timeout=20)
        # fastboot prints variables on stderr; a missing one returns non-zero.
        for line in result.output.splitlines():
            match = _VAR_LINE.match(line.strip())
            if match and match.group("key").lower() == name.lower():
                value = match.group("value").strip()
                return value
        return None

    def getvar_all(self, serial: str | None = None) -> dict[str, str]:
        result = self.runner.fastboot(["getvar", "all"], serial=serial, timeout=30)
        variables: dict[str, str] = {}
        for line in result.output.splitlines():
            match = _VAR_LINE.match(line.strip())
            if match:
                variables[match.group("key").lower()] = match.group("value").strip()
        return variables

    # -- the one write-free start ----------------------------------------- #

    def boot(self, image: Path, serial: str | None = None, timeout: float = 180) -> Result:
        image = Path(image)
        if not image.is_file() or image.stat().st_size == 0:
            raise UsageError(f"temporary boot image is missing or empty: {image}")
        return self.runner.fastboot(["boot", str(image)], serial=serial, timeout=timeout)

    def get_staged(self, local: Path, serial: str | None = None, timeout: float = 120) -> Result:
        local = Path(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        return self.runner.fastboot(["get_staged", str(local)], serial=serial, timeout=timeout)

    def reboot(self, target: str | None = None, serial: str | None = None) -> Result:
        args = ["reboot"] + ([target] if target else [])
        return self.runner.fastboot(args, serial=serial, timeout=30)
