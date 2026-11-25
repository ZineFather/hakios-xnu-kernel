# Temporary-boot compatibility — Samsung Galaxy A52s 5G (`a52sxq`)

| Question | Answer |
| --- | --- |
| Can this device run `fastboot boot`? | NO |
| Why | Samsung Galaxy A52s 5G (a52sxq) has no fastboot protocol: its bootloader is samsung-download. `fastboot boot` cannot be used, and this tool will not substitute flashing or Odin. The known alternative path (TWRP boot-image replacement, as used by the supplied z3q reference) writes the persistent boot partition and is blocked by policy. |
| Bootloader kind | samsung-download |
| Documented fastboot boot | False |
| Known alternative path | TWRP boot-image replacement, as used by the supplied z3q reference |
| Alternative path writes persistent storage | True |
| ADB state | absent |
| Fastboot state | absent |

## Evidence

LineageOS install guide for a52sxq writes every image through Download mode with samloader (Odin protocol); no fastboot step exists. HakiOS starts from `fastboot boot`, which this bootloader does not speak. The supplied z3q reference's TWRP route writes /dev/block/by-name/boot with adb shell dd; see https://github.com/ch1tmdgus/hackios-z3q/blob/main/xl.
