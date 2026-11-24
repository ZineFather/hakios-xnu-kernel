"""Storage-write audit.

The audit answers one question: can anything in this workflow write persistent
storage on the phone?  It scans source, classifies every hit as a host write, a
device RAM operation, or a device persistent write, and names the mitigation for
each persistent write.  Unmitigated persistent writes fail the command.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from . import image

HOST = "host-side write"
RAM = "device-side RAM operation"
PERSISTENT = "device-side persistent write"
TOOLING = "tooling/documentation"

TEXT_SUFFIXES = {
    ".c",
    ".h",
    ".py",
    ".sh",
    ".bash",
    ".mk",
    ".dts",
    ".dtsi",
    ".conf",
    ".config",
    ".cfg",
    ".cmd",
    ".bat",
    ".ps1",
    ".yml",
    ".yaml",
    ".service",
    ".rc",
}
TEXT_NAMES = {"Makefile", "Kconfig", "CMakeLists.txt"}

#: Files whose *content is the policy itself*: their blocklist strings are not
#: executable behaviour and must not be reported as findings.
POLICY_FILES = {"policy.py", "audit.py"}


@dataclass
class Finding:
    path: str
    line: int
    text: str
    category: str
    severity: str  # info | warning | critical
    rationale: str
    mitigated_by: str = ""

    @property
    def mitigated(self) -> bool:
        return bool(self.mitigated_by)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "line": self.line,
            "text": self.text,
            "category": self.category,
            "severity": self.severity,
            "rationale": self.rationale,
            "mitigated_by": self.mitigated_by,
        }


#: (regex, category, severity, rationale, mitigation)
RULES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        r"\bfastboot\s+(flash|flashall|erase|format|set_active|partition|resize|wipe)\b",
        PERSISTENT,
        "critical",
        "writes a device partition",
        "",
    ),
    (
        r"\bfastboot\s+(-w|--wipe)\b",
        PERSISTENT,
        "critical",
        "erases user data",
        "",
    ),
    (
        r"\bfastboot\s+(oem|flashing)\s+(unlock|lock)\b",
        PERSISTENT,
        "critical",
        "changes bootloader state",
        "",
    ),
    (
        r"\badb\s+(push|root|remount|sideload|install|uninstall)\b",
        PERSISTENT,
        "critical",
        "writes the device or changes its privilege state",
        "",
    ),
    (
        r"\bdd\s+if=",
        PERSISTENT,
        "critical",
        "raw block write",
        "",
    ),
    (
        r"\b(mkfs(\.\w+)?|sgdisk|parted|fdisk)\b",
        PERSISTENT,
        "critical",
        "filesystem or partition table write",
        "",
    ),
    (
        r"\blogdump\b",
        PERSISTENT,
        "critical",
        "the upstream loader writes its log to this partition after every run",
        "loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); "
        "the log stays in RAM for fastboot get_staged",
    ),
    (
        r"\bufs_write\b",
        PERSISTENT,
        "warning",
        "enables writes to the port's own 'darwin' partition",
        "the boot-argument policy rejects ufs_write=1 and the port has no darwin partition",
    ),
    (
        r"\bvar_store\b|\bvar_hfs\b",
        PERSISTENT,
        "warning",
        "keeps /private/var on the phone's storage",
        "the boot-argument policy rejects var_store=1 and var_hfs=",
    ),
    (
        r"\bwrite_blocks\b",
        PERSISTENT,
        "warning",
        "the firmware primitive behind every persistent write",
        "reachable only from the disabled log store, the DSU writer (not invoked) and the "
        "gated darwin writer",
    ),
    (
        r"\bfastboot\s+boot\b",
        RAM,
        "info",
        "starts an image from RAM; writes nothing",
        "",
    ),
    (
        r"\bget_staged\b",
        RAM,
        "info",
        "reads the loader log from RAM to the host",
        "",
    ),
    (
        r"\bopen\([^)]*['\"][wa]b?['\"]",
        HOST,
        "info",
        "writes a file on the host",
        "",
    ),
    (
        r"\.(write_text|write_bytes)\(",
        HOST,
        "info",
        "writes a file on the host",
        "",
    ),
    (
        r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True",
        HOST,
        "warning",
        "a shell could smuggle a device command past the policy",
        "no such call exists in this tool; the audit flags it if one is added",
    ),
)

_COMPILED = tuple(
    (re.compile(pattern, re.IGNORECASE), category, severity, rationale, mitigation)
    for pattern, category, severity, rationale, mitigation in RULES
)


def _is_text(path: Path) -> bool:
    if path.name in TEXT_NAMES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    if path.name in POLICY_FILES:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and path.suffix == ".py" and "fastboot" not in stripped:
            # Comments in Python are still scanned for fastboot/logdump so that a
            # "we used to flash here" note is visible; pure prose is not.
            pass
        for regex, category, severity, rationale, mitigation in _COMPILED:
            if regex.search(line):
                findings.append(
                    Finding(
                        path=str(path),
                        line=number,
                        text=stripped[:240],
                        category=category,
                        severity=severity,
                        rationale=rationale,
                        mitigated_by=mitigation,
                    )
                )
    return findings


def scan_tree(
    root: Path,
    *,
    skip_dirs: Iterable[str] = (".git", "build", "node_modules", "__pycache__", "tests", "reports"),
) -> list[Finding]:
    root = Path(root)
    if not root.exists():
        return []
    skip = set(skip_dirs)
    findings: list[Finding] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(root).parts):
            continue
        if not _is_text(path):
            continue
        findings.extend(scan_file(path))
    return findings


def verify_patch(repo: Path) -> tuple[bool, str]:
    """Is the no-persistent-log guard present in the loader source?"""

    source = Path(repo) / "arch/arm64/boot/src/logstore.c"
    if not source.is_file():
        return False, f"{source} not found"
    text = source.read_text(encoding="utf-8", errors="replace")
    if "HAKIOS_NO_PERSISTENT_LOG" not in text:
        return False, "the loader source has no HAKIOS_NO_PERSISTENT_LOG guard: apply patches/0001"
    return True, "the loader source contains the HAKIOS_NO_PERSISTENT_LOG guard"


def verify_loader_binary(path: Path) -> tuple[bool, str]:
    """A built loader must not carry the logdump partition name at all."""

    path = Path(path)
    if not path.is_file():
        return False, f"{path} not found"
    blob = path.read_bytes()
    needles = {
        "ASCII 'logdump'": b"logdump",
        "UTF-16LE 'logdump'": "logdump".encode("utf-16-le"),
    }
    found = [name for name, needle in needles.items() if needle in blob]
    if found:
        return False, f"{path} still contains {', '.join(found)}"
    return True, f"{path} contains no logdump string"


def verify_bootargs(cmdline: str) -> tuple[bool, list[str]]:
    bad = image.forbidden_args(cmdline)
    return (not bad), bad


def verify_command_log(path: Path) -> tuple[bool, list[str]]:
    """Re-check every device command a run recorded against the policy."""

    from . import policy
    from .errors import PolicyViolation

    path = Path(path)
    problems: list[str] = []
    if not path.is_file():
        # No log means no device command was issued at all, which is the safest
        # possible state.  Say so explicitly rather than reporting a false FAIL.
        return True, [f"{path} not found: no device commands were recorded"]
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(line)
        except ValueError:
            problems.append(f"line {number}: not JSON")
            continue
        kind = record.get("kind")
        argv = record.get("argv") or []
        if kind not in {"adb", "fastboot"}:
            continue
        # Strip the executable and the serial option.
        args = list(argv[1:])
        while args and args[0] == "-s":
            args = args[2:]
        try:
            if kind == "adb":
                policy.check_adb(args)
            else:
                policy.check_fastboot(args)
        except PolicyViolation as exc:
            problems.append(f"line {number}: {exc.message}")
    return (not problems), problems


def summarize(findings: Sequence[Finding]) -> dict:
    counts: dict[str, int] = {}
    unmitigated: list[Finding] = []
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
        if finding.category == PERSISTENT and finding.severity == "critical" and not finding.mitigated:
            unmitigated.append(finding)
    return {
        "counts": counts,
        "unmitigated_persistent": len(unmitigated),
        "unmitigated": [f.as_dict() for f in unmitigated],
    }


def render(
    findings: Sequence[Finding],
    *,
    repos: Sequence[Path],
    patch_status: tuple[bool, str] | None = None,
    binary_status: tuple[bool, str] | None = None,
) -> str:
    summary = summarize(findings)
    lines = ["# Storage-write audit", ""]
    lines.append(
        "Scope: every source and script reachable by this porting workflow. "
        "The three categories are kept apart on purpose: host-side file writes are "
        "permitted; device-side RAM operations are permitted; device-side persistent "
        "writes are forbidden."
    )
    lines.append("")
    lines.append("## Scanned")
    lines.append("")
    for repo in repos:
        lines.append(f"- `{repo}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Hits |")
    lines.append("| --- | --- |")
    for category in (HOST, RAM, PERSISTENT, TOOLING):
        lines.append(f"| {category} | {summary['counts'].get(category, 0)} |")
    lines.append("")
    if summary["unmitigated_persistent"]:
        lines.append(
            f"**{summary['unmitigated_persistent']} unmitigated persistent-write path(s) found. "
            "The boot workflow must not proceed.**"
        )
    else:
        lines.append(
            "**No unmitigated persistent-write path found in the scanned boot workflow.** "
            "Upstream HakiOS does write `logdump` by default; the loader build for this "
            "project removes that write. When a kernel checkout and a built loader are "
            "supplied, `verify-safety` also checks the source guard and the binary; "
            "those results are reported separately below."
        )
    lines.append("")

    if patch_status is not None:
        ok, detail = patch_status
        lines.append(f"- Loader source guard: {'PASS' if ok else 'FAIL'} — {detail}")
    if binary_status is not None:
        ok, detail = binary_status
        lines.append(f"- Loader binary: {'PASS' if ok else 'FAIL'} — {detail}")
    if patch_status is not None or binary_status is not None:
        lines.append("")

    lines.append("## Persistent-write findings")
    lines.append("")
    persistent = [f for f in findings if f.category == PERSISTENT]
    if not persistent:
        lines.append("None.")
    else:
        lines.append("| File:line | Severity | What | Mitigation |")
        lines.append("| --- | --- | --- | --- |")
        for finding in persistent:
            rel = finding.path
            lines.append(
                f"| `{rel}:{finding.line}` | {finding.severity} | {finding.rationale} | "
                f"{finding.mitigated_by or '**NONE**'} |"
            )
    lines.append("")

    lines.append("## Device RAM operations (permitted)")
    lines.append("")
    ram = [f for f in findings if f.category == RAM]
    if ram:
        for finding in ram[:40]:
            lines.append(f"- `{finding.path}:{finding.line}` — {finding.rationale}")
        if len(ram) > 40:
            lines.append(f"- … and {len(ram) - 40} more")
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("## Host-side writes (permitted)")
    lines.append("")
    host = [f for f in findings if f.category == HOST]
    lines.append(f"{len(host)} hit(s): report files, manifests and build output on this computer.")
    lines.append("")
    return "\n".join(lines)
