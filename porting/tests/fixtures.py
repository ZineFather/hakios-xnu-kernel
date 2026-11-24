"""Deterministic fixtures shared by the hakiosport tests.

Nothing here touches a device, a kernel checkout or the network.  Boot images are
synthetic v0 Android images with a gzip kernel that contains an XNUP payload, so
the image parsers can be exercised without a real HakiOS build.
"""

from __future__ import annotations

import gzip
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hakiosport.devices import DeviceSpec

PAGE_SIZE = 2048
XNUP_MAGIC = 0x50554E58


def synth_spec(**overrides) -> DeviceSpec:
    """A hypothetical, documented-fastboot-capable device (not the registry A52s)."""

    values = {
        "codename": "synthphone",
        "display_name": "Synthetic Test Phone",
        "manufacturer": "Example",
        "models": ("SYN-100",),
        "soc": "testsoc",
        "soc_name": "Test SoC",
        "platform": "testsoc",
        "bootloader_kind": "fastboot",
        "fastboot_boot": True,
        "known": True,
        "evidence": "synthetic fixture: fastboot boot is documented",
    }
    values.update(overrides)
    return DeviceSpec(**values)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _align16(size: int) -> int:
    return (size + 15) // 16 * 16


def make_xnup(entries) -> bytes:
    """Build the 16-byte-aligned XNUP container that ``image.parse_xnup`` reads."""

    body = bytearray()
    for name, data in entries:
        if isinstance(data, str):
            data = data.encode("utf-8")
        raw_name = name.encode("ascii")[:16].ljust(16, b"\0")
        body += raw_name + struct.pack("<II", len(data), 0) + data
        body += b"\0" * (_align16(len(data)) - len(data))
    return struct.pack("<II", XNUP_MAGIC, len(body)) + bytes(body)


@dataclass
class BootFixture:
    path: Path
    blob: bytes
    kernel: bytes
    payload: bytes
    xnup: bytes
    cmdline: str
    header_cmdline: str


def build_boot_image(
    path: Path,
    *,
    cmdline: str = "console=ttyS0 quiet",
    header_cmdline: str = "",
    magic: bytes = b"ANDROID!",
    header_version: int = 0,
    page_size: int = PAGE_SIZE,
) -> BootFixture:
    """Write a synthetic boot image and return the pieces used to build it."""

    xnup = make_xnup(
        (
            ("loader.efi", b"SYNTHETIC-EFI"),
            ("cmdline", cmdline.encode("utf-8") + b"\0"),
        )
    )
    kernel = gzip.compress(xnup, mtime=0)
    ramdisk = b"SYNTHETIC-RAMDISK"

    header = bytearray(page_size)
    header[0:8] = magic
    # Field offsets deliberately match hakiosport.image's v0 reader.
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 16, len(ramdisk))
    struct.pack_into("<I", header, 36, page_size)
    struct.pack_into("<I", header, 40, header_version)
    encoded_header = header_cmdline.encode("utf-8")[:511]
    header[64 : 64 + len(encoded_header)] = encoded_header

    def paged(data: bytes) -> bytes:
        return data + b"\0" * ((-len(data)) % page_size)

    blob = bytes(header) + paged(kernel) + paged(ramdisk)
    target = Path(path)
    target.write_bytes(blob)
    return BootFixture(
        path=target,
        blob=blob,
        kernel=kernel,
        payload=xnup,
        xnup=xnup,
        cmdline=cmdline,
        header_cmdline=header_cmdline,
    )
