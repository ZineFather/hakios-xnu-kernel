# Samsung Galaxy A52s 5G — read-only device inspection

**Collected:** 2026-11-25 over the user's ADB connection. These are observations
from the running Android system, not HakiOS test results. No boot, reboot, flash, or
partition-write operation was performed.

## Observed

| Item | Value |
| --- | --- |
| Model / device | `SM-A528B` / `a52sxq` |
| SoC | Qualcomm `SM7325` (`lahaina`), boot hardware `qcom` |
| Android | 14 |
| Root access | regular ADB shell UID 2000; read-only `su -c` queries UID 0 |
| Installed memory | boot data reports 6 GB; Linux `MemTotal` is 5,485,612 kB |
| Android display | 1080 × 2400, density 450 |
| DSI modes | 1080 × 2400 at 60 Hz and 120 Hz |
| Panel identifier in boot data | `S6E3FC3_AMS646YD01_LO_FHD`; LCD id `80000A` |
| Device tree | live `/sys/firmware/fdt` read and saved to the ignored local reports directory |
| Fastboot transport | no device enumerated by the supplied `fastboot.exe` while Android was running |

The FDT's memory entries were read, but some ranges overlap. They are preserved in
the local raw dump for engineering review and are not treated here as a validated
HakiOS memory map. The kernel-visible total above is a separate Android observation.

## Boot values still unknown

- No confirmed UEFI framebuffer base, pixel format, stride, or size was found.
- The FDT names a reserved `cont_splash_region` at `0xE1000000`, size `0x02300000`.
  This is only a reserved splash region; it has **not** been shown to be the
  framebuffer address that a UEFI loader can use.
- No verified UEFI FD base/size, payload base, A52s UEFI build, or Android boot
  image exists in this checkout.
- The stock A52s path is Samsung Download/Odin. HakiOS expects `fastboot boot`,
  which is not available through that path. The z3q TWRP procedure writes the
  persistent boot partition and is outside the no-write policy.

## Local data handling

`porting/reports/device-tree/a52sxq-device-tree.dtb` is ignored by Git and must stay
local. Raw device trees and full boot arguments can contain a serial number and
other unique identifiers; this report intentionally omits them. Only read-only
queries were used, and no phone storage was changed.

## What this means

The phone identity, basic RAM total, panel identifier and display modes are now
known well enough to improve the board notes. They do not produce a bootable image
and do not establish that any HakiOS driver works. A52s-specific UEFI support and a
bootloader path compatible with HakiOS are still absent, so there is no safe boot
attempt to make with the current artifacts.
