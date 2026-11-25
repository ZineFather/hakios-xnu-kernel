# a52sxq — Samsung Galaxy A52s 5G (SM-A528B)

| | |
| --- | --- |
| Device | Samsung Galaxy A52s 5G (`SM-A528B`, `SM-A528B/DS`, `SM-A528N`) |
| Codename | `a52sxq` |
| SoC | Qualcomm Snapdragon 778G / SM7325 (yupik; SC7280 software family) |
| Architecture | ARM64 |
| Status | **kernel and loader built in CI; never built and never booted on this phone** |

> **NO A52s BOOT IMAGE EXISTS. READ-ONLY INSPECTION ONLY.**
>
> The connected SM-A528B was inspected over ADB on 2026-11-25. Identity, memory,
> Android display modes and the Android device tree were read. No HakiOS driver was
> tested and no HakiOS boot was attempted. The stock bootloader uses Samsung
> Download/Odin, not Fastboot; HakiOS's `fastboot boot` entry path is unavailable.
>
> The supplied z3q example uses TWRP to write an Android boot image to the persistent
> `boot` partition. That method is also blocked by the no-write policy.

The successful [A52s CI run for port source commit `261db29`](https://github.com/ZineFather/hakios-xnu-kernel/actions/runs/45519914845)
publishes the kernel, loader and audit reports as separate artifacts. They are development outputs, not an install
package. See [`BUILDING.md`](BUILDING.md) for the host workflow and current image/boot blockers.

## Files

| File | Purpose |
| --- | --- |
| `device.conf` | HakiOS device record; every status is `not tested` or `unknown`. |
| `board.dts` | Phone layer. Deliberately has no unverified addresses or features. |
| `soc.dtsi` | SM7325 chip layer copied from HakiOS's official `redwood` package. Same SoC, not the same phone. |
| `configs/a52sxq_defconfig` | Includes `common_defconfig`, `sc7280.config` and `a52sxq.config`. |
| `configs/a52sxq.config` | Only `CONFIG_DEVICE="a52sxq"`; no guessed boot arguments. |
| `COMPATIBILITY.md` | Redwood-versus-a52sxq platform deltas and what remains unknown. |
| `DRIVERS.md` | Per-subsystem status; all `not tested`. |
| `DT_NOTES.md` | Where the device tree must come from and why no values were invented. |
| `firmware.conf` | What firmware is missing; no vendor blobs are included. |
| `build.sh` | Host-side build wrapper for a Linux/WSL2 checkout. It never runs a device write command. |
| `BUILDING.md` | HakiOS package workflow. |

## State

Read-only facts from the connected phone are recorded in
[`A52SXQ_DEVICE_INSPECTION.md`](../../reports/A52SXQ_DEVICE_INSPECTION.md). The raw
device tree remains local and ignored by Git because it contains device identifiers.
These observations do not validate any HakiOS driver or boot path:

| What | Feature / boot argument | State |
| --- | --- | --- |
| Device identity | SM-A528B / `a52sxq`, SM7325, Android 14 | **read-only observed** |
| Memory | 6 GB reported by boot data; `MemTotal` 5,485,612 kB | **read-only observed; HakiOS map unverified** |
| Display | 1080×2400; DSI 60/120 Hz; S6E3FC3 family | **read-only observed; UEFI framebuffer unknown** |
| Boot to the HakiOS home screen | — | **not tested** |
| Touch | — | **not tested** |
| Buttons | `buttons-pmic` / `buttons=1` | **not tested** |
| CPU frequency | `cpufreq-epss` / `cpufreq=1` | **not tested** |
| Brightness | `backlight { }` / `backlight=` | **not tested** (soft placeholder only) |
| Temperature | `thermal { }` / `thermal=` | **not tested** |
| GPU | `gpu-a660` / `gpu=1` | **not tested** |
| Sound, camera, Wi-Fi, haptics | — | **not tested** |

## What a boot would need

1. A **Fastboot-capable boot path** for this phone. The stock Samsung Download/Odin
   bootloader does not provide one. Do not substitute flashing or Odin.
2. A phone-specific **UEFI build** and its `uefi { }` framebuffer section.
3. The phone's own **device tree** (now collected read-only); its UEFI handoff values
   still need to be verified separately.
4. Firmware extracted from this phone, used only within the law and never written back.
5. A Linux/WSL2 host with the HakiOS checkout and ARM64 toolchain.
6. A supported non-persistent boot path; this Samsung does not expose HakiOS's
   required Fastboot path, so the current port cannot be started on this phone.

## Build

On Arch Linux, CachyOS, or WSL2:

```sh
export HAKIOS_KERNEL=/path/to/hakios-xnu-kernel
./build.sh --dry-run       # host-side plan only
./build.sh                 # import this package and attempt the build
```

The wrapper imports this package into the kernel checkout with HakiOS's own
`tools/device.py`, then calls `hakios_port.py build`. It never issues a fastboot
boot, flash, erase, format, slot or unlock command.

## Notes

- Redwood's haptic id and modem buffer address are Xiaomi-specific and are **not**
  copied here.
- The SoC layer being shared does not imply panel, touch, PMIC, audio, sensor or
  firmware compatibility.
- No partition, slot, bootloader state or Android installation was modified.
- See [`A52SXQ_DEVICE_INSPECTION.md`](../../reports/A52SXQ_DEVICE_INSPECTION.md),
  [`FINAL_STATUS.md`](../../reports/FINAL_STATUS.md) and
  [`storage_safety_audit.md`](../../reports/storage_safety_audit.md) for the
  host-side evidence and remaining safety blockers.
- See [`Z3Q_REFERENCE.md`](../../reports/Z3Q_REFERENCE.md) for the Snapdragon 865
  comparison and why its TWRP boot path and phone-specific UEFI data cannot be reused.
