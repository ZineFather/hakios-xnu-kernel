# Driver status — `a52sxq`

**Every subsystem is `not tested` on the Samsung Galaxy A52s 5G.** No device was
connected, no driver was built, no firmware was extracted from this phone, and no
boot image exists. The SM7325 `redwood` port is a chip-level starting point only.

| Subsystem | Starting point | Status on a52sxq |
| --- | --- | --- |
| CPU / SoC | SM7325 block layer in `soc.dtsi` | **not tested** |
| Memory | No memory layout collected | **not tested** |
| Display / framebuffer | No panel node or UEFI framebuffer value | **not tested** |
| Touch | No controller, node, firmware or polling value | **not tested** |
| Buttons | No PMIC/GPIO mapping | **not tested** |
| Storage (UFS) | No partition or UFS data collected; no writes attempted | **not tested** |
| GPU / Adreno | No GPU id or firmware verified | **not tested** |
| Audio DSP | No ADSP firmware or routing data | **not tested** |
| Speaker / microphone | No codec or amplifier data | **not tested** |
| Battery / charging | No fuel-gauge or charger readings | **not tested** |
| Wi-Fi | No WLAN firmware or module from this phone | **not tested** |
| Bluetooth | No Bluetooth firmware or module | **not tested** |
| Modem / cellular | No modem image or buffer address; Redwood's address was not copied | **not tested** |
| Sensors | No accelerometer, gyro, magnetometer, proximity, light or hall data | **not tested** |
| Fingerprint | No fingerprint device or firmware identified | **not tested** |
| Thermal | No thermal zones read | **not tested** |
| Haptics | No haptic device or id verified | **not tested** |
| Cameras / torch | No camera or flash LED data | **not tested** |

## Why nothing is marked working

"Passes host tests" is not "works on the phone". The only host-side evidence is:

- the port package passes `tools/boards.py check`;
- the Python tool's tests pass;
- the storage audit shows no unmitigated persistent write in this package.

None of those proves that a kernel driver, panel, touch controller or firmware path
works on this Samsung phone.

## Minimum bring-up order

The HakiOS porting guide's order is the only order supported by the existing code:

1. CPU frequency, thermal and SoC info.
2. Buttons, then touch.
3. UFS, read-only.
4. Adreno GPU and firmware.
5. ADSP, battery, speaker, sound and microphone.
6. Wi-Fi/QMI.
7. Haptics, camera, torch, modem, Bluetooth.
8. Remaining peripherals.

Each step requires phone-specific values measured from this device. They are not
present here and must not be guessed.
