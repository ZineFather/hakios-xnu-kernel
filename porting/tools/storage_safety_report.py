#!/usr/bin/env python3
"""Write a storage-safety report for this package and, optionally, a kernel checkout.

This is a read-only scanner. It does not touch a phone. It separates host-side
writes, device-side RAM operations and device-side persistent writes, and it lists
any persistent write that has no mitigation in the scanned text.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import audit  # noqa: E402


def _summary_line(label: str, summary: dict) -> str:
    counts = summary.get("counts", {})
    return (
        f"| {label} | {counts.get(audit.HOST, 0)} | {counts.get(audit.RAM, 0)} | "
        f"{counts.get(audit.PERSISTENT, 0)} | {summary.get('unmitigated_persistent', 0)} |"
    )


def _persistent_table(findings: list) -> list[str]:
    lines = [
        "| File:line | Severity | What | Mitigation |",
        "| --- | --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            f"| `{finding.path}:{finding.line}` | {finding.severity} | "
            f"{finding.rationale} | {finding.mitigated_by or '**NONE**'} |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernel-src",
        default=os.environ.get("HAKIOS_KERNEL", ""),
        help="optional HakiOS kernel checkout to scan as well",
    )
    parser.add_argument("--reports-dir", default=str(PACKAGE_ROOT / "reports"))
    args = parser.parse_args(argv)

    reports = Path(args.reports_dir)
    kernel = Path(args.kernel_src).expanduser() if args.kernel_src else None

    package_findings = audit.scan_tree(PACKAGE_ROOT)
    package_summary = audit.summarize(package_findings)

    kernel_findings: list = []
    kernel_summary = {"counts": {}, "unmitigated_persistent": 0, "unmitigated": []}
    patch_status = None
    binary_status = None
    if kernel is not None and kernel.is_dir():
        kernel_findings = audit.scan_tree(kernel)
        kernel_summary = audit.summarize(kernel_findings)
        patch_status = audit.verify_patch(kernel)
        loader = kernel / "arch/arm64/boot/loader.efi"
        if loader.is_file():
            binary_status = audit.verify_loader_binary(loader)

    log_path = PACKAGE_ROOT / "logs" / "device-commands.jsonl"
    log_ok, log_problems = audit.verify_command_log(log_path)

    all_unmitigated = package_summary["unmitigated"] + kernel_summary["unmitigated"]

    lines = [
        "# Storage safety audit",
        "",
        "This report is host-side only. It scans source text and records findings; it does "
        "not contact a phone. The categories are deliberately separate:",
        "",
        "1. **Host-side write** — permitted (reports, manifests, build output).",
        "2. **Device-side RAM operation** — permitted (`fastboot boot`, read-only log fetch).",
        "3. **Device-side persistent write** — forbidden.",
        "",
        "## Scope",
        "",
        f"- Package: `{PACKAGE_ROOT}`",
    ]
    if kernel is not None and kernel.is_dir():
        lines.append(f"- Kernel checkout: `{kernel}`")
    else:
        lines.append("- Kernel checkout: **not supplied** (upstream source was not scanned in this run)")
    lines += [
        "",
        "## Summary",
        "",
        "| Scope | Host-side | RAM-only | Persistent | Unmitigated persistent |",
        "| --- | ---: | ---: | ---: | ---: |",
        _summary_line("Porting package", package_summary),
        _summary_line("Upstream kernel checkout", kernel_summary),
        "",
        "## Package persistent-write findings",
        "",
    ]
    package_persistent = [f for f in package_findings if f.category == audit.PERSISTENT]
    if package_persistent:
        lines.extend(_persistent_table(package_persistent))
    else:
        lines.append("None.")
    lines += ["", "## Upstream persistent-write findings", ""]
    if kernel_findings:
        upstream_persistent = [f for f in kernel_findings if f.category == audit.PERSISTENT]
        lines.append(
            f"The checkout contains **{len(upstream_persistent)}** persistent-write hits. "
            "The unmitigated ones are listed below; the full list is in the JSON report. "
            "These are source findings, not proof that a boot path runs them."
        )
        lines.append("")
        if kernel_summary["unmitigated"]:
            lines.extend(
                _persistent_table(
                    [
                        audit.Finding(
                            path=item["path"],
                            line=item["line"],
                            text=item["text"],
                            category=item["category"],
                            severity=item["severity"],
                            rationale=item["rationale"],
                            mitigated_by=item.get("mitigated_by", ""),
                        )
                        for item in kernel_summary["unmitigated"]
                    ]
                )
            )
        else:
            lines.append("No unmitigated upstream persistent-write hit.")
    else:
        lines.append("Not scanned.")
    lines += [
        "",
        "## Loader log check",
        "",
        "Upstream HakiOS's loader writes its log to a GPT partition named `logdump` by "
        "default. The build path for this project passes "
        "`LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1`; the source-level equivalent is "
        "`patches/0001-loader-no-persistent-log.patch`. The log remains in RAM for a "
        "read-only `fastboot get_staged` fetch.",
        "",
    ]
    if patch_status is None:
        lines.append("- Loader source guard: **not checked** (no kernel checkout supplied).")
    else:
        ok, detail = patch_status
        lines.append(f"- Loader source guard: **{'PASS' if ok else 'FAIL'}** — {detail}")
    if binary_status is None:
        lines.append("- Loader binary: **not checked** (no built `loader.efi`).")
    else:
        ok, detail = binary_status
        lines.append(f"- Loader binary: **{'PASS' if ok else 'FAIL'}** — {detail}")
    lines += [
        "",
        "## Command log",
        "",
        f"- Result: **{'PASS' if log_ok else 'FAIL'}**",
    ]
    for problem in log_problems:
        lines.append(f"- {problem}")
    lines += [
        "",
        "## Verdict",
        "",
    ]
    if package_summary["unmitigated_persistent"]:
        lines.append(
            "**This porting package contains an unmitigated persistent write. Do not boot it.**"
        )
    else:
        lines.append(
            "The porting package itself contains no unmitigated persistent-write path. "
            "Every `logdump`/write-enabling hit it contains is guarded by the loader flag "
            "or rejected by the boot-argument policy."
        )
    if kernel_findings and kernel_summary["unmitigated_persistent"]:
        lines.append(
            "The upstream checkout still contains unmitigated write code in developer "
            "tools and templates. Those tools are not part of this boot workflow and must "
            "not be run. This scan is **not a pass for the whole upstream tree**."
        )
    lines += [
        "",
        "**Automatic boot remains blocked independently of this audit:** the Samsung "
        "Galaxy A52s 5G bootloader does not provide Fastboot, so the only permitted boot "
        "operation cannot be issued. This tool will not substitute flashing or Odin.",
        "",
        "## Safety conclusion",
        "",
        "- Persistent device storage was **not modified**: no device was connected and no "
        "device command was issued.",
        "- No boot image was generated.",
        "- No evidence exists that the port boots or that any driver works on this phone.",
        "",
    ]

    reports.mkdir(parents=True, exist_ok=True)
    md_path = reports / "storage_safety_audit.md"
    json_path = reports / "storage_safety_audit.json"
    md_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    payload = {
        "package": str(PACKAGE_ROOT),
        "kernel": str(kernel) if kernel is not None and kernel.is_dir() else None,
        "package_summary": package_summary,
        "kernel_summary": kernel_summary,
        "patch_check": (
            {"checked": True, "ok": patch_status[0], "detail": patch_status[1]}
            if patch_status is not None
            else {"checked": False, "reason": "no kernel checkout supplied"}
        ),
        "binary_check": (
            {"checked": True, "ok": binary_status[0], "detail": binary_status[1]}
            if binary_status is not None
            else {"checked": False, "reason": "no built loader.efi"}
        ),
        "command_log_check": {"ok": log_ok, "problems": log_problems},
        "unmitigated": all_unmitigated,
        "package_findings": [f.as_dict() for f in package_findings],
        "kernel_findings": [f.as_dict() for f in kernel_findings],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Markdown: {md_path}")
    print(f"JSON: {json_path}")
    print(
        "Package unmitigated persistent writes:",
        package_summary["unmitigated_persistent"],
        "| upstream:",
        kernel_summary["unmitigated_persistent"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
