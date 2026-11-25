"""Device identity, registry and boot-capability rules.

Nothing in the generic code knows a phone by name: callers pass a query, this
module resolves it to a :class:`DeviceSpec`.  A phone that is not in the registry
still resolves (to an ``unknown`` spec) so that ``inspect`` can describe it; the
boot flow then refuses because no port and no verified capability exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


@dataclass(frozen=True)
class DeviceSpec:
    codename: str
    display_name: str
    manufacturer: str
    models: tuple[str, ...] = ()
    soc: str = ""
    soc_name: str = ""
    soc_family: str = ""
    platform: str = ""
    bootloader_kind: str = "unknown"  # "fastboot" | "samsung-download" | "unknown"
    fastboot_boot: bool | None = None  # None: not established
    alternate_boot_path: str = ""
    alternate_boot_path_writes_persistent_storage: bool | None = None
    aliases: tuple[str, ...] = ()
    evidence: str = ""
    notes: str = ""
    known: bool = True

    def matches(self, query: str) -> bool:
        q = _norm(query)
        if not q:
            return False
        values = {
            self.codename,
            self.display_name,
            self.manufacturer + self.display_name,
            *self.models,
            *self.aliases,
        }
        return any(_norm(v) == q for v in values if v)

    def as_dict(self) -> dict:
        return {
            "codename": self.codename,
            "display_name": self.display_name,
            "manufacturer": self.manufacturer,
            "models": list(self.models),
            "soc": self.soc,
            "soc_name": self.soc_name,
            "soc_family": self.soc_family,
            "platform": self.platform,
            "bootloader_kind": self.bootloader_kind,
            "fastboot_boot": self.fastboot_boot,
            "alternate_boot_path": self.alternate_boot_path,
            "alternate_boot_path_writes_persistent_storage":
                self.alternate_boot_path_writes_persistent_storage,
            "known": self.known,
            "evidence": self.evidence,
            "notes": self.notes,
        }


#: The registry.  Adding a phone is data, not code.
#:
#: a52sxq facts and where each comes from:
#:  * codename a52sxq, models SM-A528B / SM-A528B-DS / SM-A528N:
#:    LineageOS device tree (android_device_samsung_a52sxq, BoardConfig.mk
#:    TARGET_OTA_ASSERT_DEVICE := a52sxq) and the LineageOS install page.
#:  * SoC SM7325 (Snapdragon 778G): LineageOS BoardConfig includes
#:    device/samsung/sm7325-common/BoardConfigCommon.mk, and the HakiOS redwood
#:    package (also SM7325) carries soc.dtsi "Qualcomm Snapdragon 778G (SM7325, yupik)".
#:  * bootloader: Samsung Download mode / Odin protocol.  The LineageOS install
#:    procedure for this exact device uses Download mode and samloader for every
#:    write; it never invokes fastboot.  HakiOS's entry path is `fastboot boot`,
#:    which this bootloader does not implement.
REGISTRY: tuple[DeviceSpec, ...] = (
    DeviceSpec(
        codename="a52sxq",
        display_name="Samsung Galaxy A52s 5G",
        manufacturer="Samsung",
        models=("SM-A528B", "SM-A528B/DS", "SM-A528N"),
        soc="sm7325",
        soc_name="Qualcomm Snapdragon 778G",
        soc_family="SM7325 / yupik (SC7280 software family)",
        platform="sm7325",
        bootloader_kind="samsung-download",
        fastboot_boot=False,
        alternate_boot_path="TWRP boot-image replacement, as used by the supplied z3q reference",
        alternate_boot_path_writes_persistent_storage=True,
        aliases=("Galaxy A52s 5G", "a52sxq", "A52s"),
        evidence=(
            "LineageOS install guide for a52sxq writes every image through Download "
            "mode with samloader (Odin protocol); no fastboot step exists. "
            "HakiOS starts from `fastboot boot`, which this bootloader does not speak. "
            "The supplied z3q reference's TWRP route writes /dev/block/by-name/boot "
            "with adb shell dd; see https://github.com/ch1tmdgus/hackios-z3q/blob/main/xl."
        ),
        notes=(
            "Same SoC as the HakiOS redwood reference port, so the SoC layer is "
            "reusable; the phone layer (panel, touch, PMIC rails, UEFI) is not. "
            "The z3q TWRP method requires a persistent boot-partition write and is "
            "therefore blocked by this port's storage policy."
        ),
    ),
)


@dataclass
class Capability:
    supported: bool
    reason: str
    evidence: str = ""
    checks: dict = field(default_factory=dict)


def resolve(query: str | None, ports_dir: Path | None = None) -> DeviceSpec:
    """Resolve a human name, model or codename to a spec.

    Order: registry match, then a port directory of that codename, then an
    ``unknown`` spec whose codename is a slug of the query.
    """

    if query:
        for spec in REGISTRY:
            if spec.matches(query):
                return spec

        slug = re.sub(r"[^a-z0-9-]+", "-", query.lower()).strip("-")
        if ports_dir and slug and (ports_dir / slug / "board.dts").is_file():
            return DeviceSpec(
                codename=slug,
                display_name=query,
                manufacturer="",
                known=False,
                evidence="resolved from devices/ directory, not the registry",
            )
        return DeviceSpec(
            codename=slug or "unknown",
            display_name=query,
            manufacturer="",
            known=False,
            evidence="not in the registry; identity must come from the device",
        )

    # No query: use the single port present, if there is exactly one.
    if ports_dir and ports_dir.is_dir():
        candidates = sorted(p.name for p in ports_dir.iterdir() if (p / "board.dts").is_file())
        if len(candidates) == 1:
            for spec in REGISTRY:
                if spec.codename == candidates[0]:
                    return spec
            return DeviceSpec(
                codename=candidates[0],
                display_name=candidates[0],
                manufacturer="",
                known=False,
                evidence="the only port in devices/",
            )

    raise ValueError(
        "no device given and no single port in devices/: pass --device \"Samsung Galaxy A52s 5G\" "
        "or --codename a52sxq"
    )


# --------------------------------------------------------------------------- #
# identity
# --------------------------------------------------------------------------- #

#: Android properties that identify the phone, in order of reliability.
IDENTITY_PROPS = (
    "ro.product.device",
    "ro.product.vendor.device",
    "ro.boot.hardware",
    "ro.product.model",
    "ro.product.vendor.model",
    "ro.board.platform",
    "ro.boot.bootloader",
    "ro.bootloader",
    "ro.build.fingerprint",
    "ro.build.version.release",
    "ro.build.version.security_patch",
    "ro.boot.verifiedbootstate",
    "ro.boot.flash.locked",
    "ro.boot.vbmeta.device_state",
    "ro.boot.slot_suffix",
)


def identity_from_props(props: Mapping[str, str]) -> dict:
    return {key: props.get(key, "") for key in IDENTITY_PROPS if props.get(key)}


def verify_identity(spec: DeviceSpec, props: Mapping[str, str]) -> tuple[bool, list[str]]:
    """Compare what the phone reports with the requested spec.

    Returns ``(ok, reasons)``.  A mismatch is a refusal, never a warning: booting
    another phone's image is the failure this check exists to prevent.
    """

    if not spec.known:
        return False, [f"device {spec.display_name!r} is not a known port"]

    device = (props.get("ro.product.device") or props.get("ro.product.vendor.device") or "").lower()
    model = (props.get("ro.product.model") or props.get("ro.product.vendor.model") or "").upper()
    hardware = (props.get("ro.boot.hardware") or "").lower()
    platform = (props.get("ro.board.platform") or "").lower()

    reasons: list[str] = []
    if device and device != spec.codename:
        reasons.append(f"ro.product.device is {device!r}, expected {spec.codename!r}")
    if model and spec.models and model not in {m.upper() for m in spec.models}:
        reasons.append(f"ro.product.model is {model!r}, expected one of {spec.models}")
    if hardware and spec.codename and hardware not in {spec.codename, spec.platform, spec.soc}:
        # ro.boot.hardware is often the SoC family on Qualcomm phones (e.g. "sm7325").
        if hardware not in {spec.platform, spec.soc}:
            reasons.append(f"ro.boot.hardware is {hardware!r}, expected {spec.codename!r} or its SoC")
    if platform and spec.platform and platform != spec.platform:
        reasons.append(f"ro.board.platform is {platform!r}, expected {spec.platform!r}")

    if not device and not model:
        reasons.append("the phone reported no product identity")

    return (not reasons), reasons


# --------------------------------------------------------------------------- #
# boot capability
# --------------------------------------------------------------------------- #


def capability(
    spec: DeviceSpec,
    *,
    fastboot_seen: bool,
    fastboot_vars: Mapping[str, str] | None = None,
) -> Capability:
    """Decide whether ``fastboot boot`` may be attempted, and why not if not.

    The decision is conservative and device-agnostic: it only allows a boot when
    the phone is a known port whose bootloader is documented to implement the
    fastboot protocol, a fastboot device is actually present, and the bootloader
    reports itself unlocked.
    """

    variables = {k.lower(): v for k, v in (fastboot_vars or {}).items()}
    checks = {
        "known_port": spec.known,
        "bootloader_kind": spec.bootloader_kind,
        "documented_fastboot_boot": spec.fastboot_boot,
        "alternate_boot_path": spec.alternate_boot_path or None,
        "alternate_boot_path_writes_persistent_storage": spec.alternate_boot_path_writes_persistent_storage,
        "fastboot_device_present": fastboot_seen,
        "unlocked": variables.get("unlocked"),
        "product": variables.get("product"),
    }

    if not spec.known:
        return Capability(
            False,
            "the device is not a known HakiOS port; no image can be matched to it",
            spec.evidence,
            checks,
        )

    if spec.fastboot_boot is False:
        alternate_path_note = ""
        if (
            spec.alternate_boot_path
            and spec.alternate_boot_path_writes_persistent_storage
        ):
            alternate_path_note = (
                f" The known alternative path ({spec.alternate_boot_path}) writes "
                "the persistent boot partition and is blocked by policy."
            )
        return Capability(
            False,
            f"{spec.display_name} ({spec.codename}) has no fastboot protocol: its "
            f"bootloader is {spec.bootloader_kind}. `fastboot boot` cannot be used, "
            "and this tool will not substitute flashing or Odin."
            + alternate_path_note,
            spec.evidence,
            checks,
        )

    if spec.fastboot_boot is None:
        return Capability(
            False,
            "it is not established that this device's bootloader implements `fastboot boot`",
            spec.evidence,
            checks,
        )

    if not fastboot_seen:
        return Capability(
            False,
            "no device is in fastboot mode (the bootloader has not exposed a fastboot interface)",
            spec.evidence,
            checks,
        )

    product = variables.get("product")
    if product and _norm(product) not in {_norm(spec.codename), _norm(spec.display_name)}:
        return Capability(
            False,
            f"the fastboot device reports product {product!r}, not {spec.codename!r}",
            spec.evidence,
            checks,
        )

    unlocked = (variables.get("unlocked") or "").lower()
    if unlocked and unlocked not in {"yes", "true", "1", "unlocked"}:
        return Capability(
            False,
            f"the bootloader reports unlocked={unlocked!r}; refusing to touch a locked device",
            spec.evidence,
            checks,
        )

    return Capability(
        True,
        "the device is a known port with a fastboot bootloader, present and unlocked",
        spec.evidence,
        checks,
    )


def find_port(spec: DeviceSpec, ports_dir: Path) -> Path | None:
    candidate = ports_dir / spec.codename
    if (candidate / "board.dts").is_file():
        return candidate
    return None
