"""Hardware inspection over read-only ADB.

Every value in the report carries the command it came from and a confidence tag.
If a value cannot be read, it is recorded as ``unknown`` with the reason.  Nothing
is inferred from a similar phone and nothing is filled in from a datasheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from .adb import Adb
from .devices import DeviceSpec, identity_from_props, verify_identity


@dataclass
class Observation:
    key: str
    value: str
    source: str
    confidence: str = "reported"  # reported | derived | unknown

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class HardwareReport:
    spec: DeviceSpec
    identity: dict = field(default_factory=dict)
    identity_ok: bool = False
    identity_reasons: list[str] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    raw_props: dict = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)
    device_present: bool = False
    fastboot_vars: dict = field(default_factory=dict)
    fdt_saved: str = ""

    def add(self, key: str, value: str, source: str, confidence: str = "reported") -> None:
        self.observations.append(Observation(key, value, source, confidence))

    def get(self, key: str) -> str:
        for obs in self.observations:
            if obs.key == key:
                return obs.value
        return "unknown"

    def section(self, prefix: str) -> list[Observation]:
        return [o for o in self.observations if o.key.startswith(prefix)]

    def as_dict(self) -> dict:
        return {
            "device_present": self.device_present,
            "spec": self.spec.as_dict(),
            "identity_ok": self.identity_ok,
            "identity_reasons": self.identity_reasons,
            "identity": self.identity,
            "observations": [o.as_dict() for o in self.observations],
            "fastboot_vars": self.fastboot_vars,
            "fdt_saved": self.fdt_saved,
            "raw_props": self.raw_props,
            "commands": self.commands,
        }


# --------------------------------------------------------------------------- #
# parsers (pure: tested against fixtures)
# --------------------------------------------------------------------------- #


def parse_cpuinfo(text: str) -> dict[str, str]:
    """Summarise /proc/cpuinfo without inventing topology."""

    cores = len(re.findall(r"^processor\s*:", text, re.MULTILINE))
    hardware = ""
    implementer = ""
    parts: list[str] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "hardware" and not hardware:
            hardware = value
        elif key == "cpu implementer" and not implementer:
            implementer = value
        elif key == "cpu part" and value not in parts:
            parts.append(value)
    summary = {
        "cores": str(cores) if cores else "unknown",
        "hardware": hardware or "unknown",
        "implementer": implementer or "unknown",
        "cpu_parts": ",".join(parts) if parts else "unknown",
    }
    return summary


def parse_meminfo(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^(?P<key>[A-Za-z_()]+):\s+(?P<num>\d+)\s*(?P<unit>kB)?", line.strip())
        if match:
            values[match.group("key")] = match.group("num") + (" kB" if match.group("unit") else "")
    return values


def parse_wm_size(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
    if match:
        out["width"] = match.group(1)
        out["height"] = match.group(2)
    match = re.search(r"Override size:\s*(\d+)x(\d+)", text)
    if match:
        out["override_width"] = match.group(1)
        out["override_height"] = match.group(2)
    return out


def parse_battery(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key in {"level", "status", "health", "present", "technology", "temperature", "voltage", "charge_counter"}:
            out[key] = value.strip()
    return out


def parse_touch_devices(input_dump: str) -> list[str]:
    """Names of input devices whose class suggests a touchscreen."""

    names: list[str] = []
    for match in re.finditer(r"^\s*Device\s+\d+:\s*(?P<name>.+)$", input_dump, re.MULTILINE):
        name = match.group("name").strip()
        lowered = name.lower()
        if any(word in lowered for word in ("touch", "goodix", "focaltech", "synaptics", "atmel", "stm", "sec_touch")):
            if name not in names:
                names.append(name)
    return names


def parse_sensors(sensors_dump: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"^\s*\d+\)\s*(?P<name>[^|]+)\|", sensors_dump, re.MULTILINE):
        name = match.group("name").strip()
        if name and name not in names:
            names.append(name)
    return names


def parse_by_name(listing: str) -> dict[str, str]:
    """``ls -l /dev/block/by-name`` -> {name: target}."""

    mapping: dict[str, str] = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "->" in line:
            name = parts[-3] if parts[-2] == "->" else ""
            target = parts[-1]
            if name:
                mapping[name] = target
    return mapping


def parse_partitions(text: str) -> list[dict]:
    parts: list[dict] = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[0].isdigit():
            parts.append(
                {
                    "major": fields[0],
                    "minor": fields[1],
                    "blocks": fields[2],
                    "name": fields[3],
                }
            )
    return parts


def parse_soc_files(files: Mapping[str, str]) -> dict[str, str]:
    wanted = {
        "machine": "machine",
        "family": "family",
        "soc_id": "soc_id",
        "revision": "revision",
        "platform": "platform",
        "vendor": "vendor",
    }
    out: dict[str, str] = {}
    for key, text in files.items():
        if key in wanted and text.strip():
            out[key] = text.strip()
    return out


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

#: Read-only commands used by ``inspect``.  Each is validated by the policy layer
#: before it runs; the list is data so that a reviewer can see it in one place.
INSPECT_COMMANDS = (
    "uname -a",
    "cat /proc/cpuinfo",
    "cat /proc/meminfo",
    "cat /proc/partitions",
    "cat /sys/devices/soc0/machine",
    "cat /sys/devices/soc0/family",
    "cat /sys/devices/soc0/soc_id",
    "cat /sys/devices/soc0/revision",
    "cat /sys/devices/soc0/platform",
    "cat /sys/devices/soc0/vendor",
    "ls -l /dev/block/by-name",
    "ls /sys/class/net",
    "ls /sys/bus/platform/devices",
    "wm size",
    "wm density",
    "dumpsys battery",
    "dumpsys input",
    "dumpsys sensorservice",
)

_SOC_FILES = ("machine", "family", "soc_id", "revision", "platform", "vendor")


def collect(
    adb: Adb,
    spec: DeviceSpec,
    *,
    serial: str | None = None,
    fdt_dir: Path | None = None,
    fastboot_vars: Mapping[str, str] | None = None,
    runner=None,
) -> HardwareReport:
    """Collect everything readable.  A failed read is recorded, never fatal."""

    report = HardwareReport(spec=spec, fastboot_vars=dict(fastboot_vars or {}))
    device = adb.single(serial)
    report.device_present = True

    props = adb.getprop(device.serial)
    report.raw_props = props
    report.identity = identity_from_props(props)
    report.identity_ok, report.identity_reasons = verify_identity(spec, props)

    for key, value in report.identity.items():
        report.add(f"identity.{key}", value, f"adb:getprop {key}")

    if not props:
        report.add("identity.note", "getprop returned nothing", "adb:getprop", "unknown")

    soc_files: dict[str, str] = {}
    for command in INSPECT_COMMANDS:
        result = adb.shell(command, serial=device.serial)
        ok = result.ok and bool(result.stdout.strip())
        if not ok:
            report.add(f"command.{command}", "not readable", f"adb shell {command}", "unknown")
            continue
        text = result.stdout
        if command.startswith("cat /sys/devices/soc0/"):
            soc_files[command.rsplit("/", 1)[-1]] = text
        elif command == "cat /proc/cpuinfo":
            for key, value in parse_cpuinfo(text).items():
                report.add(f"soc.cpu.{key}", value, "adb:cat /proc/cpuinfo", "derived")
        elif command == "cat /proc/meminfo":
            mem = parse_meminfo(text)
            for key in ("MemTotal", "MemFree", "MemAvailable", "SwapTotal"):
                if key in mem:
                    report.add(f"memory.{key}", mem[key], "adb:cat /proc/meminfo")
        elif command == "cat /proc/partitions":
            partitions = parse_partitions(text)
            report.add(
                "storage.partition_count",
                str(len(partitions)),
                "adb:cat /proc/partitions",
                "derived",
            )
        elif command == "ls -l /dev/block/by-name":
            names = parse_by_name(text)
            report.add("storage.by_name_count", str(len(names)), "adb:ls -l /dev/block/by-name", "derived")
            for name in sorted(names):
                report.add(f"storage.partition.{name}", names[name], "adb:ls -l /dev/block/by-name")
        elif command == "ls /sys/class/net":
            report.add("connectivity.interfaces", " ".join(text.split()), "adb:ls /sys/class/net")
        elif command == "ls /sys/bus/platform/devices":
            report.add("platform.devices_count", str(len(text.split())), "adb:ls /sys/bus/platform/devices", "derived")
        elif command == "wm size":
            size = parse_wm_size(text)
            if size:
                report.add("display.width", size.get("width", "unknown"), "adb:wm size")
                report.add("display.height", size.get("height", "unknown"), "adb:wm size")
        elif command == "wm density":
            match = re.search(r"(\d+)", text)
            if match:
                report.add("display.density_dpi", match.group(1), "adb:wm density")
        elif command == "dumpsys battery":
            for key, value in parse_battery(text).items():
                report.add(f"power.{key}", value, "adb:dumpsys battery")
        elif command == "dumpsys input":
            touches = parse_touch_devices(text)
            report.add(
                "input.touch_devices",
                ", ".join(touches) if touches else "none reported",
                "adb:dumpsys input",
                "derived" if touches else "unknown",
            )
        elif command == "dumpsys sensorservice":
            sensors = parse_sensors(text)
            report.add(
                "sensors.reported",
                ", ".join(sensors) if sensors else "none parsed",
                "adb:dumpsys sensorservice",
                "derived" if sensors else "unknown",
            )
        elif command == "uname -a":
            report.add("os.uname", text.strip(), "adb:uname -a")

    for key, value in parse_soc_files(soc_files).items():
        report.add(f"soc.{key}", value, f"adb:cat /sys/devices/soc0/{key}")

    # The device tree is the single most useful artefact for a port.  It is often
    # readable without root; when it is not, say so.
    if fdt_dir is not None:
        target = Path(fdt_dir) / f"{spec.codename}-device-tree.dtb"
        if adb.pull("/sys/firmware/fdt", target, serial=device.serial):
            saved_as = (Path(Path(fdt_dir).name) / target.name).as_posix()
            report.fdt_saved = saved_as
            report.add("devicetree.saved", saved_as, "adb:pull /sys/firmware/fdt")
        else:
            report.add(
                "devicetree.saved",
                "not readable without root (do not root the phone to get it)",
                "adb:pull /sys/firmware/fdt",
                "unknown",
            )

    # Gaps are stated explicitly so that the report cannot be mistaken for a
    # complete hardware description.
    for gap in (
        "soc.revision",
        "display.panel_model",
        "display.refresh_hz",
        "input.touch_controller",
        "storage.controller",
        "connectivity.wifi_chip",
        "connectivity.bluetooth_chip",
        "other.audio_dsp",
    ):
        if report.get(gap) == "unknown":
            report.add(gap, "not established from read-only inspection", "gap", "unknown")

    return report
