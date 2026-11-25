# Compatibility notes — `a52sxq` versus `redwood` (SM7325)

**Status: structural research only. No driver, panel, PMIC, firmware or boot path was
verified on the Samsung Galaxy A52s 5G.**

Both phones use Qualcomm Snapdragon 778G / SM7325, so the **chip-level block map** can
be shared. The **phone-level wiring is different** and must be measured from an
`a52sxq` device tree, not copied from Redwood.

| Area | Redwood (POCO X5 Pro 5G) | a52sxq (Galaxy A52s 5G) | Status |
| --- | --- | --- | --- |
| SoC | SM7325 | SM7325 / Snapdragon 778G | Same family; exact revision unverified here |
| Bootloader entry | Fastboot path used by HakiOS | Samsung Download/Odin; **no Fastboot** | **Blocker**: `fastboot boot` unavailable |
| TWRP alternative | Not applicable | The supplied z3q reference replaces the persistent `boot` image from TWRP | **Blocked by policy**: writes the phone's boot partition |
| UEFI | Redwood UEFI package exists upstream | No a52sxq UEFI build in this package | Missing |
| Panel | Redwood panel node and timing | 6.5" Super AMOLED, 1080x2400, 120 Hz nominal — **exact panel node unverified** | Not tested |
| Display controller | Redwood DSI/MDP wiring | Same SoC blocks, different panel and board wiring | Not tested |
| Touch | Redwood touch controller | Samsung-specific controller and firmware **unknown** | Not tested |
| Buttons | Redwood PMIC mapping | Samsung PMIC/GPIO mapping **unknown** | Not tested |
| PMIC / rails | Redwood regulator tree | Samsung board rails **unknown**; do not copy | Not tested |
| Haptics | Redwood haptic id 5 | **Do not copy**; no id verified | Unknown |
| Audio | Redwood codec/amplifier wiring | Samsung codec/amplifier wiring **unknown** | Not tested |
| Modem | Redwood modem buffer address | **Do not copy**; no address verified | Not tested |
| Wi-Fi / BT | Redwood firmware paths | Samsung firmware paths **unknown** | Not tested |
| Cameras | Redwood camera nodes | Samsung camera nodes **unknown** | Not tested |
| Sensors | Redwood sensor set | Samsung sensor set **unknown** | Not tested |
| Fingerprint | Redwood device | Samsung device **unknown** | Not tested |
| Battery / charging | Redwood fuel gauge | Samsung charger/fuel gauge **unknown** | Not tested |
| Firmware | Redwood vendor files | Must come from an a52sxq phone; not included | Missing |

## Shared and non-shared files

- `soc.dtsi` is the official HakiOS SM7325 layer from the `redwood` package.
- `board.dts` is intentionally empty of phone values: `features = <>;` and only a
  soft backlight placeholder.
- `configs/a52sxq.config` deliberately contains no Redwood boot arguments.
- Redwood's haptic id and modem buffer address are explicitly excluded.

## What would change this status

1. A legitimate Fastboot-capable boot path for `a52sxq`.
2. The device tree and basic memory/display facts have now been collected read-only;
   the UEFI framebuffer handoff and peripheral wiring remain unknown.
3. An a52sxq UEFI build with a verified framebuffer.
4. Drivers and firmware for the Samsung panel, touch, PMIC, audio, sensors and modem.
5. A successful RAM-only boot, observed on the phone.

Until all five exist, this is **not a compatible port**, only a correctly labelled
starting point.

The z3q comparison and the TWRP write analysis are documented in
[`porting/reports/Z3Q_REFERENCE.md`](../../reports/Z3Q_REFERENCE.md).
