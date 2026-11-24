# Hardware report — Samsung Galaxy A52s 5G (`a52sxq`)

Collected by `hakios_port.py inspect` over read-only ADB. Every value names the command it came from. `unknown` means it could not be read; it is not a guess.

| Field | Value |
| --- | --- |
| Device present | no |
| Registry entry | yes |
| Codename | a52sxq |
| Manufacturer | Samsung |
| Models | SM-A528B, SM-A528B/DS, SM-A528N |
| SoC (registry) | Qualcomm Snapdragon 778G |
| SoC family | SM7325 / yupik (SC7280 software family) |
| Identity verified | no |

> **No device was inspected.** No adb device was reachable, so no hardware value was collected. Nothing in this file is inferred from the model name.

## Gaps

| Key | Why it is unknown |
| --- | --- |
| inspection.status | no adb device was inspected: adb is not installed or not on PATH |
| inspection.fastboot | no fastboot variables were read (state: tool-missing) |
| inspection.note | adb is not installed or not on PATH; no Android identity was read |
| inspection.note | fastboot is not installed or not on PATH; no bootloader variables were read |
| inspection.note | a52sxq uses the samsung-download bootloader, which does not implement fastboot; a normal reboot preserves the stock installation |
