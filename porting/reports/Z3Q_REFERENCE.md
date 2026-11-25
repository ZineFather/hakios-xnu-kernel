# z3q reference findings for the A52s port

Reviewed the current `main` README and z3q-specific notes in the user-supplied repository, along with its device configuration and launcher behavior.

## What carries over

- The current repository reports an iOS 16/XNU home-screen boot on the S20 Ultra using a system image loaded into RAM, with some touch, key, graphics, CPU and Wi-Fi support. It is useful evidence for the architecture, not evidence that the A52s can use the z3q binaries.
- Its broad sequence is a useful reference: device-specific UEFI starts the HakiOS loader; the loader stages a system payload in RAM; XNU starts with a minimal hardware set, then drivers are enabled incrementally.
- The `xl ramdisk` example is the system-image transfer after the phone-side loader path is already established. It does not mean the entire z3q boot chain can start on an A52s without installing or otherwise loading a device-specific UEFI/loader.
- Its porting notes call out the right classes of inputs to collect independently: the phone's own device tree, UEFI drivers extracted from its own firmware, its UEFI memory map, and its display/framebuffer details.

## What does not carry over

| Item | z3q reference | A52s (`a52sxq`) | Decision |
| --- | --- | --- | --- |
| SoC | Snapdragon 865 / SM8250, Adreno 650 | Snapdragon 778G / SM7325, Adreno 642L | Different platform generation; do not copy phone or SoC constants |
| Entry method | Samsung TWRP path; z3q setup installs a boot image and later sends the system image over USB into RAM | Samsung Download/Odin; no Fastboot boot transport was found on the connected A52s | Persistent TWRP install is blocked by the no-write rule; RAM system image transfer is a later stage, not a replacement for the boot chain |
| UEFI | Samsung z3q package and drivers from the z3q `xbl.img` | No A52s UEFI package or A52s-extracted firmware here | Build and verify for A52s independently |
| Device tree | z3q DTB, board-id 15 | Live A52s FDT collected read-only; no A52s UEFI boot DTB/descriptor verified | Keep the A52s dump local; do not copy or edit the z3q DTB |
| Memory and display | z3q-specific `FD_BASE`, `FD_SIZE`, `PAYLOAD_BASE`, and framebuffer | A52s has 6 GB boot memory report, 1080×2400 60/120 Hz DSI, and a reserved splash range; UEFI framebuffer base/format/stride remain unknown | Do not reuse z3q addresses or treat the splash range as a verified framebuffer |
| Kernel drivers | z3q touch, power, display and peripheral details | A52s wiring and firmware are not verified | Reuse concepts only after checking A52s sources and hardware |

## Why TWRP is not a RAM-only boot here

The current z3q README says Samsung uses TWRP, not generic `fastboot boot`. Its
documented setup installs a custom boot image, then uses a volume key and USB loader
commands for later test runs. The launcher path inspected for this reference also
copies an Android boot image to TWRP `/tmp` and runs:

```sh
dd if=/tmp/xl-boot.img of=/dev/block/by-name/boot bs=4096 conv=fsync
```

It reads the boot partition back afterwards and asks the user to restore a backup
to return to Android. The `/tmp` file is temporary, but the destination is the
persistent boot partition. The z3q-specific notes also describe shrinking `/data`
and editing GPT entries to carve a Darwin partition. Those actions are not safe to
copy to this A52s. The current porting policy allows only `fastboot boot
<temporary image>` and forbids partition writes; the A52s has no documented Fastboot
boot path, so this z3q procedure cannot be used.

## Work that would move A52s closer to a boot

1. Identity and an Android FDT have now been collected over read-only ADB; the raw tree stays local because it contains identifiers.
2. Obtain only A52s-matched firmware inputs on the host, subject to their applicable terms.
3. Port/build a dedicated A52s UEFI and loader description; framebuffer and UEFI handoff values are still unverified.
4. Build an image only after those inputs are present; the current `board.dts` intentionally lacks loader/UEFI sections.
5. Identify and verify a temporary boot method that does not write a phone partition. The A52s has no documented Fastboot boot path, and the z3q TWRP setup writes `boot`, so no permitted boot route is established yet.

The z3q repository is a reference for research and design; its binaries, DTB,
memory addresses, firmware, board description, partition procedure and boot entry
are not A52s artifacts. See its [current README](https://github.com/ch1tmdgus/hackios-z3q)
and [z3q hardware notes](https://github.com/ch1tmdgus/hackios-z3q/blob/main/docs/Z3Q.md).
