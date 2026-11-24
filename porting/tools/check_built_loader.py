#!/usr/bin/env python3
"""Check a freshly built UEFI loader against the RAM-only logging rule.

This is the narrow CI check: it looks at the loader source guard and the built
``loader.efi`` only. It deliberately does **not** scan the whole kernel tree,
because upstream developer tools contain unrelated write helpers that this
workflow never runs. Use ``hakios_port.py verify-safety`` for the package scoped
audit and ``tools/storage_safety_report.py`` for the full, honest tree report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport import audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernel-src",
        default=".",
        help="HakiOS kernel checkout that was just built (default: .)",
    )
    parser.add_argument(
        "--loader",
        default="",
        help="path to loader.efi (default: <kernel-src>/arch/arm64/boot/loader.efi)",
    )
    args = parser.parse_args(argv)

    kernel = Path(args.kernel_src).expanduser().resolve()
    loader = Path(args.loader).expanduser() if args.loader else kernel / "arch/arm64/boot/loader.efi"

    problems: list[str] = []

    source_ok, source_detail = audit.verify_patch(kernel)
    print(f"loader source guard: {'PASS' if source_ok else 'FAIL'} - {source_detail}")
    if not source_ok:
        problems.append(source_detail)

    if not loader.is_file():
        problems.append(f"no built loader at {loader}")
        print(f"loader binary: FAIL - not found at {loader}")
    else:
        binary_ok, binary_detail = audit.verify_loader_binary(loader)
        print(f"loader binary: {'PASS' if binary_ok else 'FAIL'} - {binary_detail}")
        if not binary_ok:
            problems.append(binary_detail)

    if problems:
        print("loader check: FAIL")
        for problem in problems:
            print(" - " + problem)
        return 1
    print("loader check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
