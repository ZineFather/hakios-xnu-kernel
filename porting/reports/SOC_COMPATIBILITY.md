# SoC compatibility — SM7325 / Snapdragon 778G

**Status: structural compatibility only; not tested on hardware.**

| Item | Verified statement |
| --- | --- |
| Target device | Samsung Galaxy A52s 5G, models SM-A528B / SM-A528B/DS / SM-A528N, codename `a52sxq`. |
| Target SoC | Qualcomm Snapdragon 778G / SM7325 (registry name `sm7325`, software family `SM7325 / yupik (SC7280 software family)`). |
| SoC layer source | `devices/a52sxq/soc.dtsi` is the SM7325 layer taken from HakiOS's official `redwood` package, which uses the same SoC. |
| Phone layer | `devices/a52sxq/board.dts` is deliberately empty of unverified addresses and features (`features = <>;` with only a soft backlight placeholder). Redwood's phone-specific values were **not** copied. |
| Config fragments | `configs/a52sxq_defconfig` includes `common_defconfig`, `sc7280.config` and `a52sxq.config`. `a52sxq.config` sets only `CONFIG_DEVICE="a52sxq"`; no unverified boot arguments are added. |
| Explicit warning from the package | Redwood's haptic id (5) and modem buffer address belong to a different phone and must not be copied into an A52s configuration. No addresses were guessed here. |
| UEFI | No UEFI build for `a52sxq` exists in this package. The upstream image step needs the phone's own `uefi { }` section and UEFI build; neither is present here. |
| Hardware validation | None. No device was connected, no kernel was built, no boot was attempted. |

## What "same SoC" does and does not mean

The shared SM7325 layer is a **starting point only**: it describes chip-level blocks that the redwood package already carries. Panel, touch, PMIC rails, firmware and UEFI are phone-specific and remain unknown for this board. Nothing in this file asserts that a driver works, that an address is correct, or that an image would boot.

Evidence for the boot path itself is separate: see `BOOT_COMPATIBILITY.md` and the generated `boot-compatibility.md`.
