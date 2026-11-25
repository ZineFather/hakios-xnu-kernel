# Temporary-boot compatibility — Samsung Galaxy A52s 5G (`a52sxq`)

**Verdict: NO. This phone cannot run `fastboot boot`, and the tool has no flashing, Odin, or TWRP write fallback.**

The authoritative tool-generated report is `boot-compatibility.md` (lowercase); this file summarises and cross-references it. `boot-result.json` records the refusal with `started: false`.

## Confirmed blocker

Samsung Galaxy A52s 5G / SM-A528B (`a52sxq`) uses the **Samsung Download / Odin** bootloader, not fastboot. The tool's capability gate refuses before constructing or sending any boot command, including in `--dry-run`, and a unit test confirms the refusal even if a fastboot device is present. Exit code is **3** (`UnsupportedHardware`), not a build or device error.

The supplied z3q reference uses TWRP, but its `xl` script copies the image to
`/tmp` and then runs `dd` to `/dev/block/by-name/boot`, permanently replacing
Android's boot image. The same script reads the partition back afterwards; verification
does not make it a RAM-only boot. This conflicts with the project's absolute no-partition-write
rule, so the A52s tool records this route as a known persistent-write path and refuses it.
See [`Z3Q_REFERENCE.md`](Z3Q_REFERENCE.md).

Evidence recorded in the reports:

- LineageOS's [a52sxq install guide](https://wiki.lineageos.org/devices/a52sxq/install/) writes every image in Download mode with samloader (Odin protocol), with no fastboot step.
- HakiOS's only entry path is `fastboot boot` (see its `arch/arm64/boot/README.md`). The two protocols do not match.

The bootloader is already unlocked. This tool never unlocks, locks, flashes, erases, formats, changes slots or writes partitions, and it will not substitute Odin or TWRP for the refused boot.

## Commands actually observed

`hakios_port.py --codename a52sxq boot --dry-run` exited **3**; the message states that no flashing or Odin substitution will occur. Because the capability gate fires first, no read-only device probing was attempted on this boot path, and `logs/` contains no device-command log. `inspect` separately reported `adb state: absent`, `fastboot state: tool-missing`, and that no device was inspected.

## Not tested

No boot image was generated, no boot was attempted, no device was connected, and no hardware was tested. This report establishes only that the tool refuses this device safely — not that any alternative boot method exists or works.
