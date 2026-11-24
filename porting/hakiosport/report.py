"""Markdown/JSON report rendering.  Host-side writes only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from .devices import Capability, DeviceSpec
from .inspect import HardwareReport
from .image import BootImageInfo


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_json(path: Path, data: object) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_hardware(report: HardwareReport) -> str:
    spec = report.spec
    lines: list[str] = []
    lines.append(f"# Hardware report — {spec.display_name} (`{spec.codename}`)")
    lines.append("")
    lines.append(
        "Collected by `hakios_port.py inspect` over read-only ADB. Every value names the "
        "command it came from. `unknown` means it could not be read; it is not a guess."
    )
    lines.append("")
    lines.append(
        table(
            ["Field", "Value"],
            [
                ["Device present", "yes" if report.device_present else "no"],
                ["Registry entry", "yes" if spec.known else "no"],
                ["Codename", spec.codename],
                ["Manufacturer", spec.manufacturer or "unknown"],
                ["Models", ", ".join(spec.models) or "unknown"],
                ["SoC (registry)", spec.soc_name or "unknown"],
                ["SoC family", spec.soc_family or "unknown"],
                ["Identity verified", "yes" if report.identity_ok else "no"],
            ],
        )
    )
    if report.identity_reasons:
        lines.append("")
        lines.append("Identity problems:")
        for reason in report.identity_reasons:
            lines.append(f"- {reason}")
    if not report.device_present:
        lines.append("")
        lines.append(
            "> **No device was inspected.** No adb device was reachable, so no hardware "
            "value was collected. Nothing in this file is inferred from the model name."
        )

    groups = [
        ("Processor and platform", "soc."),
        ("Memory", "memory."),
        ("Storage (read-only)", "storage."),
        ("Display", "display."),
        ("Input", "input."),
        ("Power and battery", "power."),
        ("Connectivity", "connectivity."),
        ("Sensors", "sensors."),
        ("Device tree", "devicetree."),
        ("Platform devices", "platform."),
        ("Identity properties", "identity."),
    ]
    for title, prefix in groups:
        rows = report.section(prefix)
        if not rows:
            continue
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        lines.append(table(["Key", "Value", "Source", "Confidence"], [[o.key, o.value, o.source, o.confidence] for o in rows]))

    lines.append("")
    lines.append("## Gaps")
    lines.append("")
    gaps = [o for o in report.observations if o.confidence == "unknown"]
    if gaps:
        lines.append(table(["Key", "Why it is unknown"], [[o.key, o.value] for o in gaps]))
    else:
        lines.append("None recorded.")
    lines.append("")
    return "\n".join(lines)


def render_boot_compatibility(
    spec: DeviceSpec,
    capability: Capability,
    *,
    detection: dict,
    image: BootImageInfo | None = None,
) -> str:
    lines = [f"# Temporary-boot compatibility — {spec.display_name} (`{spec.codename}`)", ""]
    lines.append(
        table(
            ["Question", "Answer"],
            [
                ["Can this device run `fastboot boot`?", "YES" if capability.supported else "NO"],
                ["Why", capability.reason],
                ["Bootloader kind", spec.bootloader_kind],
                ["Documented fastboot boot", spec.fastboot_boot],
                ["ADB state", detection.get("adb_state", "not detected")],
                ["Fastboot state", detection.get("fastboot_state", "not detected")],
            ],
        )
    )
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    lines.append(capability.evidence or "No evidence recorded.")
    lines.append("")
    if detection.get("adb_identity"):
        lines.append("## Identity as the phone reports it")
        lines.append("")
        lines.append(table(["Property", "Value"], detection["adb_identity"].items()))
        lines.append("")
    if detection.get("fastboot_vars"):
        lines.append("## Fastboot variables (read-only)")
        lines.append("")
        lines.append(
            table(
                ["Variable", "Value"],
                sorted(detection["fastboot_vars"].items()),
            )
        )
        lines.append("")
    if image is not None:
        lines.append("## Image under test")
        lines.append("")
        lines.append(
            table(
                ["Field", "Value"],
                [
                    ["Path", image.path],
                    ["Size", f"{image.size} bytes"],
                    ["SHA-256", image.sha256],
                    ["Kind", image.kind],
                    ["Header version", image.header_version],
                    ["Payload entries", ", ".join(image.payload_entries) or "none found"],
                    ["Payload cmdline", image.payload_cmdline or "(empty)"],
                    ["Valid", "yes" if image.valid else "no"],
                ],
            )
        )
        if image.reasons:
            lines.append("")
            lines.append("Problems:")
            for reason in image.reasons:
                lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines)
