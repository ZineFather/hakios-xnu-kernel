# Driver status — Samsung Galaxy A52s 5G (`a52sxq`)

**Every subsystem below is `not tested` on this phone.** No device was connected, no driver was built, no firmware was extracted from this phone, and no boot image was produced. The SM7325 reference port (`redwood`, same SoC) is a **starting point only**: it supplies the chip-level `soc.dtsi` layer in `devices/a52sxq/soc.dtsi`, not verified phone-specific behaviour.

| Subsystem | Starting point / what is known | Status on this phone |
| --- | --- | --- |
| CPU / SoC | SM7325 layer from HakiOS's official `redwood` package (same SoC); `soc = "sm7325"` in `board.dts`. | **not tested** |
| Memory | No value collected; `inspect` reported no device and no adb identity. | **not tested** |
| Display / panel | No phone-specific panel or brightness values; `board.dts` has only a soft-backlight placeholder and no verified address. | **not tested** |
| Touch | No touch controller or node identified for this board. | **not tested** |
| Buttons | No PMIC button mapping verified; redwood values were not copied. | **not tested** |
| GPU | No GPU driver or firmware tested here. | **not tested** |
| Storage (UFS) | No partitions, slots or writes touched; no phone-specific storage data collected. | **not tested** |
| Audio | No codec, amplifier or routing data collected. | **not tested** |
| Wi-Fi | No firmware or module from this phone. | **not tested** |
| Bluetooth | No firmware or module from this phone. | **not tested** |
| Modem | No modem image or buffer address; the config explicitly refuses to copy redwood's modem buffer address. | **not tested** |
| Sensors | No sensor nodes identified. | **not tested** |
| Battery / charging | No fuel-gauge or charger data collected. | **not tested** |
| Fingerprint | No fingerprint device or firmware identified. | **not tested** |

## Why nothing is marked as working

"Compiles", "passes host tests" and "seen working on the phone" are different claims. Only host-side checks happened here: 52 unit tests pass and the port package passes a structural check. Neither is evidence about a driver on the A52s. The generated `hardware.md` and `a52sxq_hardware_report.md` record all hardware fields as unknown and state that no device was inspected; `boot-result.json` records `started: false`.
