# a52sxq — Samsung Galaxy A52s 5G (SM-A528B)

| | |
| --- | --- |
| Device | Samsung Galaxy A52s 5G (`SM-A528B`, `SM-A528B/DS`, `SM-A528N`) |
| Codename | `a52sxq` |
| SoC | Qualcomm Snapdragon 778G / SM7325 (yupik; SC7280 software family) |
| Architecture | ARM64 |
| Status | **scaffold only — never built and never booted on this phone** |

> **NO BOOT IMAGE EXISTS. NO HARDWARE WAS TESTED.**
>
> This phone's stock bootloader is Samsung Download/Odin, not Fastboot. HakiOS's only
> entry path is `fastboot boot`, so the port cannot be started on this phone through
> the permitted RAM-only path. No flashing or Odin fallback is provided.

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

Say what was seen on the phone and what was not. Nothing has been seen on this phone:

| What | Feature / boot argument | State |
| --- | --- | --- |
| Boot to the home screen | — | **not tested** |
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
3. The phone's own **device tree**, read over ADB or from its boot image.
4. Firmware extracted from this phone, used only within the law and never written back.
5. A Linux/WSL2 host with the HakiOS checkout and ARM64 toolchain.
6. A verified `fastboot boot` attempt; until then the port is unproven.

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
- See `reports/FINAL_STATUS.md` and `reports/storage_safety_audit.md` for the
  host-side evidence and the remaining safety blockers.
