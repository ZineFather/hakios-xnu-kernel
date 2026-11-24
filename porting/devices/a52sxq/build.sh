#!/usr/bin/env bash
# Build wrapper for the a52sxq HakiOS device package.
#
# This is a HOST-SIDE build script. It never starts, flashes, erases, formats, unlocks
# or changes a slot on the phone. The only device-side boot operation in this project
# is the Python tool's `fastboot boot <existing local image>`, and on this Samsung
# Download/Odin phone even that path is refused by the capability gate.
#
# Usage (Arch Linux, CachyOS, or WSL2):
#   export HAKIOS_KERNEL=/path/to/hakios-xnu-kernel
#   ./build.sh --dry-run
#   ./build.sh
#
# Any remaining arguments are passed to `hakios_port.py build`.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
kernel_src="${HAKIOS_KERNEL:-}"

if [[ -z "${kernel_src}" ]]; then
    echo "error: set HAKIOS_KERNEL to a HakiOS xnu-kernel checkout" >&2
    exit 2
fi

if [[ ! -f "${kernel_src}/Makefile" ]]; then
    echo "error: ${kernel_src} is not a HakiOS kernel checkout (no Makefile)" >&2
    exit 2
fi

if [[ ! -f "${kernel_src}/tools/device.py" ]]; then
    echo "error: ${kernel_src} has no tools/device.py; use the official common branch" >&2
    exit 2
fi

# A dry run must not modify even the kernel checkout, so it goes straight to the
# host-side planner. A real run first imports this package into the checkout, which
# is a host-side write only.
if [[ " ${*:-} " == *" --dry-run "* ]]; then
    exec python3 "${repo_root}/hakios_port.py" \
        --codename a52sxq \
        --kernel-src "${kernel_src}" \
        build "$@"
fi

python3 "${kernel_src}/tools/device.py" add a52sxq --from "${here}"
python3 "${kernel_src}/tools/boards.py" check

exec python3 "${repo_root}/hakios_port.py" \
    --codename a52sxq \
    --kernel-src "${kernel_src}" \
    build "$@"
