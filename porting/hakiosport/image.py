"""Android boot image and HakiOS XNUP payload inspection.

This is how the tool proves what it is about to boot: the image type, its header,
its SHA-256, and — when a HakiOS payload is present — the exact kernel command
line embedded in it.  A command line that would enable persistent writes is a
refusal, not a warning.
"""

from __future__ import annotations

import gzip
import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

#: Boot arguments that turn on a persistent device write.  HakiOS gates its two
#: storage writers on these; a RAM-only boot must not carry any of them.
FORBIDDEN_BOOTARGS = (
    "ufs_write=1",
    "var_store=1",
    "var_hfs=",
    "root_apfs=",
    "dsu_write=",
)

ANDROID_MAGIC = b"ANDROID!"
VENDOR_MAGIC = b"VNDRBOOT"
XNUP_MAGIC = 0x50554E58


@dataclass
class XnupEntry:
    name: str
    size: int
    data: bytes


@dataclass
class BootImageInfo:
    path: str
    size: int
    sha256: str
    kind: str = "unknown"  # android | vendor_boot | unknown
    header_version: int | None = None
    page_size: int | None = None
    kernel_size: int | None = None
    ramdisk_size: int | None = None
    cmdline: str = ""
    payload_entries: list[str] = field(default_factory=list)
    payload_cmdline: str = ""
    valid: bool = False
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "kind": self.kind,
            "header_version": self.header_version,
            "page_size": self.page_size,
            "kernel_size": self.kernel_size,
            "ramdisk_size": self.ramdisk_size,
            "cmdline": self.cmdline,
            "payload_entries": self.payload_entries,
            "payload_cmdline": self.payload_cmdline,
            "valid": self.valid,
            "reasons": self.reasons,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_xnup(blob: bytes, start: int = 0) -> list[XnupEntry] | None:
    """Parse an XNUP container at ``start``; ``None`` when there is not one."""

    if start + 8 > len(blob):
        return None
    magic, size = struct.unpack_from("<II", blob, start)
    if magic != XNUP_MAGIC:
        return None
    end = start + 8 + size
    if size == 0 or end > len(blob):
        return None
    entries: list[XnupEntry] = []
    offset = start + 8
    while offset + 24 <= end:
        raw_name = blob[offset : offset + 16]
        name = raw_name.split(b"\0", 1)[0].decode("ascii", "replace")
        entry_size, _reserved = struct.unpack_from("<II", blob, offset + 16)
        if not name:
            break
        data_start = offset + 24
        data_end = data_start + entry_size
        if data_end > end:
            return None
        entries.append(XnupEntry(name=name, size=entry_size, data=blob[data_start:data_end]))
        offset = data_start + ((entry_size + 15) // 16) * 16
    return entries


def _gunzip_prefix(blob: bytes) -> bytes | None:
    """Decompress the gzip stream at the start of ``blob``, ignoring trailing data."""

    if len(blob) < 2 or blob[0] != 0x1F or blob[1] != 0x8B:
        return None
    try:
        return gzip.decompress(blob)
    except OSError:
        pass
    try:
        decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
        return decomp.decompress(blob) + decomp.flush()
    except zlib.error:
        return None


def find_payload_cmdline(decompressed: bytes) -> tuple[list[str], str]:
    """Find the XNUP payload inside a decompressed boot shim blob."""

    # The container is 16-byte aligned by construction; scan on that grid first,
    # then fall back to a byte scan (bounded, the blob is at most a few MiB).
    candidates = list(range(0, len(decompressed) - 8, 16))
    for offset in candidates:
        entries = parse_xnup(decompressed, offset)
        if entries:
            names = [entry.name for entry in entries]
            cmdline = ""
            for entry in entries:
                if entry.name == "cmdline":
                    cmdline = entry.data.split(b"\0", 1)[0].decode("utf-8", "replace")
            if "loader.efi" in names or "kernel" in names or cmdline:
                return names, cmdline
    index = decompressed.find(struct.pack("<I", XNUP_MAGIC))
    while index != -1:
        entries = parse_xnup(decompressed, index)
        if entries:
            names = [entry.name for entry in entries]
            cmdline = ""
            for entry in entries:
                if entry.name == "cmdline":
                    cmdline = entry.data.split(b"\0", 1)[0].decode("utf-8", "replace")
            return names, cmdline
        index = decompressed.find(struct.pack("<I", XNUP_MAGIC), index + 1)
    return [], ""


def forbidden_args(cmdline: str) -> list[str]:
    found: list[str] = []
    for arg in cmdline.split():
        for forbidden in FORBIDDEN_BOOTARGS:
            if arg == forbidden or (forbidden.endswith("=") and arg.startswith(forbidden)):
                found.append(arg)
    return found


def inspect_boot_image(path: Path) -> BootImageInfo:
    path = Path(path)
    info = BootImageInfo(path=str(path), size=0, sha256="")
    if not path.is_file():
        info.reasons.append("file does not exist")
        return info

    blob = path.read_bytes()
    info.size = len(blob)
    info.sha256 = sha256_file(path)

    if len(blob) < 64:
        info.reasons.append("file is too small to be a boot image")
        return info

    if blob[:8] == ANDROID_MAGIC:
        info.kind = "android"
        info.header_version = struct.unpack_from("<I", blob, 40)[0]
        if info.header_version not in (0, 1, 2, 3, 4):
            info.reasons.append(f"unsupported Android header version {info.header_version}")
        if info.header_version in (0, 1, 2):
            # boot_img_hdr_v0: kernel_size@8, ramdisk_size@16, page_size@36,
            # cmdline[512]@64.  v1 adds recovery_dtbo fields; v2 adds dtb fields.
            info.kernel_size = struct.unpack_from("<I", blob, 8)[0]
            info.ramdisk_size = struct.unpack_from("<I", blob, 16)[0]
            info.page_size = struct.unpack_from("<I", blob, 36)[0]
            info.cmdline = blob[64 : 64 + 512].split(b"\0", 1)[0].decode("utf-8", "replace")
            kernel_offset = info.page_size or 2048
            if info.kernel_size and kernel_offset + info.kernel_size <= len(blob):
                kernel = blob[kernel_offset : kernel_offset + info.kernel_size]
                decompressed = _gunzip_prefix(kernel)
                if decompressed:
                    info.payload_entries, info.payload_cmdline = find_payload_cmdline(decompressed)
        else:
            # boot_img_hdr_v3/v4: kernel_size@8, ramdisk_size@12, cmdline[1536]@44,
            # fixed 4096-byte pages, no kernel gzip wrapper of the v0 shape.
            info.kernel_size = struct.unpack_from("<I", blob, 8)[0]
            info.ramdisk_size = struct.unpack_from("<I", blob, 12)[0]
            info.page_size = 4096
            info.cmdline = blob[44 : 44 + 1536].split(b"\0", 1)[0].decode("utf-8", "replace")
        info.valid = not info.reasons
    elif blob[:8] == VENDOR_MAGIC:
        info.kind = "vendor_boot"
        # vendor_boot_img_hdr_v3: version@8, page_size@12
        info.header_version = struct.unpack_from("<I", blob, 8)[0]
        info.page_size = struct.unpack_from("<I", blob, 12)[0]
        info.valid = True
    else:
        info.reasons.append(
            "not an Android boot image (expected 'ANDROID!' or 'VNDRBOOT' at offset 0)"
        )
        return info

    if info.size < 2048:
        info.reasons.append("image is smaller than one page")
        info.valid = False

    bad = forbidden_args(info.payload_cmdline)
    if bad:
        info.reasons.append(
            "payload command line enables persistent writes: " + " ".join(bad)
        )
        info.valid = False

    return info
