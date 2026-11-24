# Temporary-boot compatibility — Samsung Galaxy A52s 5G (`a52sxq`)

| Question | Answer |
| --- | --- |
| Can this device run `fastboot boot`? | NO |
| Why | Samsung Galaxy A52s 5G (a52sxq) has no fastboot protocol: its bootloader is samsung-download. `fastboot boot` cannot be used, and this tool will not substitute flashing or Odin. |
| Bootloader kind | samsung-download |
| Documented fastboot boot | False |
| ADB state | tool-missing |
| Fastboot state | tool-missing |

## Evidence

LineageOS install guide for a52sxq writes every image through Download mode with samloader (Odin protocol); no fastboot step exists. HakiOS starts from `fastboot boot`, which this bootloader does not speak.
