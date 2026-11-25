# Device-tree notes — `a52sxq`

## What is committed

- `soc.dtsi` — the SM7325 chip layer from HakiOS's official `redwood` package.
  It describes chip-level blocks shared by SM7325 boards.
- `board.dts` — the phone layer. It deliberately contains no measured addresses,
  no panel node, no touch node, no PMIC rails and no `uefi { }` section.
- `configs/a52sxq.config` — only `CONFIG_DEVICE="a52sxq"`. No boot arguments are
  invented.

## What is not committed

The phone's **own** Android device tree, vendor firmware, boot image and UEFI build
are not in this package. They are vendor material and must be obtained from the
phone and handled under the applicable licences.

## How to obtain the real tree, read-only

The host-side `inspect` command now attempts this read-only pull
automatically when an ADB device is reachable. Its default destination is
`porting/reports/device-tree/a52sxq-device-tree.dtb` (change the report
directory with `--reports-dir` if needed). The project ignores `*.dtb`, so the
phone's device tree stays local instead of being committed.

On a Linux host with `adb` and an authorized phone, run from the kernel checkout:

```sh
python3 porting/hakios_port.py --codename a52sxq inspect
```

The command also records identity and hardware observations. When connected in
TWRP, ADB must show the device as ready; recovery may not expose every Android
property, so missing fields remain marked unknown. If `/sys/firmware/fdt` is
unreadable, **do not root the phone**. Use another read-only source, such as a
matching stock boot image, or stop and report that the tree could not be obtained.

## How to use it

The HakiOS workflow imports the resulting tree with its own tooling:

```sh
tools/hakios-device.py new a52sxq --soc sc7280 --fdt a52sxq.dtb
```

Then every value in `board.dts` must be checked against the dumped tree and, where
necessary, measured on the phone. A value that is an SoC fact belongs in `soc.dtsi`
(or the kernel defaults); a value that is this phone's belongs in `board.dts` or in
this device's own driver.

## Rules

- Never copy Redwood's panel, touch, PMIC, haptic id, modem buffer address or
  firmware paths into this package.
- Never add an address that was not read from this phone or a trusted source.
- A node is not marked working because it compiles; it is marked working only after
  it is observed on the phone.
- A RAM-only boot requires a Fastboot-capable bootloader. The stock Samsung
  Download/Odin path does not provide one.
