"""Read-only ADB client.

Only the commands permitted by :mod:`hakiosport.policy` are reachable from here.
The client never roots the phone, never remounts, and never pushes anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import UsageError
from .runner import CommandRunner, Result


@dataclass
class AdbDevice:
    serial: str
    state: str
    product: str = ""
    model: str = ""
    device: str = ""
    transport_id: str = ""

    @property
    def ready(self) -> bool:
        return self.state == "device"


_DEVICE_LINE = re.compile(r"^(?P<serial>\S+)\s+(?P<state>\S+)(?P<rest>.*)$")
_PROP_LINE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]$")


class Adb:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    # -- discovery -------------------------------------------------------- #

    def devices(self) -> list[AdbDevice]:
        result = self.runner.adb(["devices", "-l"])
        if not result.ok:
            raise UsageError("adb devices failed", detail=result.tail())
        found: list[AdbDevice] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("*"):
                continue
            match = _DEVICE_LINE.match(line)
            if not match:
                continue
            rest = match.group("rest") or ""
            fields = dict(
                part.split(":", 1) for part in rest.split() if ":" in part
            )
            found.append(
                AdbDevice(
                    serial=match.group("serial"),
                    state=match.group("state"),
                    product=fields.get("product", ""),
                    model=fields.get("model", ""),
                    device=fields.get("device", ""),
                    transport_id=fields.get("transport_id", ""),
                )
            )
        return found

    def single(self, serial: str | None = None) -> AdbDevice:
        devices = [d for d in self.devices() if d.ready]
        if serial:
            for device in devices:
                if device.serial == serial:
                    return device
            raise UsageError(f"no ready adb device with serial {serial!r}")
        if not devices:
            raise UsageError(
                "no adb device in the 'device' state. Connect the phone, enable USB "
                "debugging, and accept the host key on the phone."
            )
        if len(devices) > 1:
            raise UsageError(
                "more than one adb device is connected; pass --serial "
                + ", ".join(d.serial for d in devices)
            )
        return devices[0]

    # -- reads ------------------------------------------------------------ #

    def getprop(self, serial: str | None = None) -> dict[str, str]:
        result = self.runner.adb(["shell", "getprop"], serial=serial)
        if not result.ok:
            raise UsageError("getprop failed", detail=result.tail())
        props: dict[str, str] = {}
        for line in result.stdout.splitlines():
            match = _PROP_LINE.match(line.strip())
            if match:
                props[match.group("key")] = match.group("value")
        return props

    def shell(self, command: str, *, serial: str | None = None, timeout: float | None = None) -> Result:
        return self.runner.adb(["shell", command], serial=serial, timeout=timeout)

    def shell_text(self, command: str, *, serial: str | None = None) -> str:
        result = self.shell(command, serial=serial)
        return result.stdout if result.ok else ""

    def pull(self, remote: str, local: Path, *, serial: str | None = None) -> bool:
        local = Path(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        result = self.runner.adb(["pull", remote, str(local)], serial=serial, timeout=120)
        return result.ok and local.is_file()

    def reboot(self, target: str | None = None, *, serial: str | None = None) -> Result:
        args = ["reboot"] + ([target] if target else [])
        return self.runner.adb(args, serial=serial, timeout=30)

    # -- convenience ------------------------------------------------------ #

    def identity(self, serial: str | None = None) -> dict[str, str]:
        from .devices import identity_from_props

        return identity_from_props(self.getprop(serial))
