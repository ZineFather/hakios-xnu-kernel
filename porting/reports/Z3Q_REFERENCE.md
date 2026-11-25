# z3q reference findings for the A52s port

Reviewed the user-supplied [ch1tmdgus/hackios-z3q repository](https://github.com/ch1tmdgus/hackios-z3q), especially its README, `common/devices/z3q.conf`, `xl`, `docs/PORTING.md`, and `docs/Z3Q.md`.

## What carries over

- It is useful evidence that a Samsung Qualcomm device can run this style of XNU/HakiOS stack once a device-specific boot chain, UEFI, loader, device tree, and drivers exist.
- Its broad sequence is a useful reference: device-specific UEFI starts the HakiOS loader; the loader stages a system payload in RAM; XNU starts with a minimal hardware set, then drivers are enabled incrementally.
- Its porting notes call out the right classes of inputs to collect independently: the phone's own device tree, UEFI drivers extracted from its own firmware, its UEFI memory map, and its display/framebuffer details.

## What does not carry over

| Item | z3q reference | A52s (`a52sxq`) | Decision |
| --- | --- | --- | --- |
| SoC | Snapdragon 865 / SM8250, Adreno 650 | Snapdragon 778G / SM7325, Adreno 642L | Different platform generation; do not copy phone or SoC constants |
| Entry method | TWRP replaces the persistent Android `boot` image | Samsung Download/Odin; `fastboot boot` is not documented | TWRP path is blocked under the no-write rule |
| UEFI | Samsung z3q package and drivers from the z3q `xbl.img` | No A52s UEFI package or extracted A52s firmware here | Build and verify for A52s independently |
| Device tree | z3q DTB, board-id 15 | No A52s DTB collected in this task | Do not copy or edit the z3q DTB |
| Memory and display | z3q-specific `FD_BASE`, `FD_SIZE`, `PAYLOAD_BASE`, and framebuffer | A52s values not read from this phone | Do not reuse these addresses |
| Kernel drivers | z3q touch, power, display and peripheral details | A52s wiring and firmware are not verified | Reuse concepts only after checking A52s sources and hardware |

## Why TWRP is not a RAM-only boot here

In the supplied repository, `xl enter` calls `enter_twrp()`, which builds an image
and calls `flash_boot()`. That function verifies the Android boot-image header,
pushes a temporary copy to recovery's `/tmp`, then runs:

```sh
dd if=/tmp/xl-boot.img of=/dev/block/by-name/boot bs=4096 conv=fsync
```

It reads the boot partition back afterwards and asks the user to restore a backup
to return to Android. The temporary copy in `/tmp` does not change the fact that
the destination is persistent storage. The current porting policy allows only
`fastboot boot <temporary image>` as a device-side boot operation and forbids all
partition writes, so neither this TWRP sequence nor a restore-after-boot variant
is permitted.

## Work that would move A52s closer to a boot

1. Capture A52s identity, device tree, and platform information with read-only methods.
2. Obtain only A52s-matched firmware inputs on the host, subject to their applicable terms.
3. Port/build a dedicated A52s UEFI and loader description, including measured memory and framebuffer values.
4. Build the image only after those inputs are present; the current `board.dts` intentionally lacks a loader section.
5. Identify and verify a temporary boot method that does not write a phone partition. The known stock Samsung Download path is not fastboot, and the supplied TWRP path writes `boot`, so no permitted boot route is established yet.

The z3q repository is a reference for research and design; its binaries, DTB,
memory addresses, firmware, board description, and boot procedure are not A52s
artifacts.
