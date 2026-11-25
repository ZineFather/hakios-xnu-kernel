# A52s build, debug, and boot status

This guide is specific to the Samsung Galaxy A52s 5G (`a52sxq`, SM-A528B). It documents the host-side bring-up
workflow and its current limits. It does **not** provide a flash or install procedure.

## Current state

| Stage | State |
| --- | --- |
| Device package and board-table integration | Checked by CI |
| ARM64 XNU kernel | Built successfully in CI; includes the `a52sxq` board entry |
| AArch64 UEFI loader | Built successfully in CI with persistent log writes disabled and checked |
| Android boot image | Not generated; verified A52s UEFI platform values are missing |
| Physical A52s boot | Not attempted; no device was connected during these builds |
| Flash/install | Unsupported and prohibited by this port's storage policy |

The successful [A52s workflow](https://github.com/ZineFather/hakios-xnu-kernel/actions/runs/45519914845) publishes
three temporary artifacts: `a52sxq-kernel`, `a52sxq-loader`, and `a52sxq-audit`. The kernel/loader artifact is
useful for inspection and continued development; it is not an Android boot image and cannot be installed on the
phone. Artifacts expire after 14 days.

## How the port is put together

The device package under `porting/devices/a52sxq/` provides the board-specific input to the shared kernel tree:

1. `soc.dtsi` describes the SM7325 SoC layer, reused as a structural starting point from the same-SoC Redwood
   package. It does not establish that Redwood's board wiring or firmware matches the Samsung phone.
2. `board.dts` describes the phone. Unmeasured memory, framebuffer, peripheral, and firmware values remain absent.
3. `tools/device.py add` imports the package into the kernel checkout, and `tools/boards.py check` validates the
   package and generated board tables.
4. The kernel build produces an ARM64 Mach-O kernel. The loader build produces an AArch64 UEFI PE image.
5. The loader is built with `HAKIOS_NO_PERSISTENT_LOG`; a binary check rejects it if the persistent `logdump`
   write string remains. CI stores build outputs and audit reports as separate artifacts.
6. An Android boot image can only be assembled after a correct A52s UEFI build and the phone's measured loader
   platform description are present. The current `board.dts` intentionally has no `loader { }` block, so the
   image builder must not guess those values.

These checks prove the host build and package structure only. They do not prove that the display, input, storage,
power, or any other driver works on a physical A52s.

## Host setup

Build on Linux, macOS, or Linux under WSL2. Native Windows is not a supported kernel/loader build host. For Ubuntu
or WSL2 Ubuntu, install the tools used by the build workflow:

```sh
sudo apt update
sudo apt install -y clang lld make git python3 adb fastboot autoconf automake libtool gawk
```

The repository's kernel build scripts may require additional platform dependencies; use their reported missing
tool as the source of truth. Keep generated artifacts and any vendor firmware local. Do not commit raw device
dumps, proprietary firmware, signing material, or personal identifiers.

## Inspect and validate

Run from the root of this repository. The inspect step is read-only on the phone; it records missing tools or an
unconnected phone as missing data rather than inventing values. Enable Android USB debugging and authorize this
computer before connecting a phone for inspection.

```sh
# Read Android identity and, when available, save the device tree to host reports.
python3 porting/hakios_port.py --codename a52sxq inspect

# Check the device package and generated port files.
python3 porting/hakios_port.py --codename a52sxq port

# See host/toolchain/source blockers without running a build.
python3 porting/hakios_port.py --codename a52sxq build --dry-run

# Audit the package, source guard, available loader binary, and recorded device commands.
python3 porting/hakios_port.py --codename a52sxq verify-safety --kernel-src .
```

Reports are written under `porting/reports/`. The inspected device tree, if collected, stays on the host in the
ignored `porting/reports/device-tree/` directory. Review reports before sharing them; remove serial numbers and
other personal identifiers. A passing package audit is not a hardware or boot pass.

## Reproduce the CI kernel and loader build

From the repository root, run the same host-side build stages used by CI:

```sh
python3 porting/tests/run_tests.py
python3 tools/device.py add a52sxq --from porting/devices/a52sxq
python3 tools/boards.py check
make kernel
LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1 make loader
python3 porting/tools/check_built_loader.py --kernel-src .
```

Expected outputs include `../xnu-12377-hakios/BUILD/obj/mach.development.bcm2837` and
`arch/arm64/boot/loader.efi`. The workflow uploads both in `a52sxq-kernel`; `a52sxq-loader` contains the loader
from the Linux build job. Do not infer boot compatibility from filenames, successful compilation, or a board-table
entry.

For a clean machine, the [A52s workflow definition](../../../.github/workflows/build-a52sxq.yml) is the canonical
build recipe. The CI jobs never contact a phone or execute device commands.

## Image, boot, and storage policy

The A52s stock bootloader uses Samsung Download/Odin. This port has no verified `fastboot boot` route for the
phone, and the project tool refuses the A52s boot command with exit code **3** before issuing a device command.
There is no safe flash or install step in this guide.

Do not substitute Odin, TWRP, `dd`, partition writes, slot changes, or bootloader unlocks. The supplied z3q
reference uses TWRP to write its persistent `boot` partition, and is not a RAM-only boot method. See
[`Z3Q_REFERENCE.md`](../../reports/Z3Q_REFERENCE.md).

Before an image could be considered, the port still needs measured A52s device-tree and memory data, a phone-specific
UEFI build, verified framebuffer and payload values, and a documented non-persistent boot path supported by this
device. The SM8250 z3q addresses and DTB cannot fill gaps for this SM7325 phone. Until those prerequisites are met,
the image builder remains intentionally unused and no physical boot should be attempted.

## Troubleshooting sequence

1. Run `inspect`; resolve `adb` missing, unauthorized, or offline states before interpreting absent device data.
2. Run `port` and `tools/boards.py check`; fix structural package errors before compiling.
3. Run the kernel and loader stages separately. Keep their console output and CI run link with any bug report.
4. Run `check_built_loader.py`; stop if the persistent log guard does not pass.
5. Inspect `porting/reports/build-plan.json`, `build-report.json`, `storage-audit.json`, and
   `boot-compatibility.md` to see which stage is blocked.
6. Do not work around an unsupported boot gate with a flash, recovery, or Download-mode write.

## Related device notes

- [`README.md`](README.md) — device facts and tested-versus-unknown status.
- [`COMPATIBILITY.md`](COMPATIBILITY.md) — SM7325 reuse boundaries and missing board data.
- [`DT_NOTES.md`](DT_NOTES.md) — device-tree sources and interpretation notes.
- [`DRIVERS.md`](DRIVERS.md) — subsystem-by-subsystem state.
- [`firmware.conf`](firmware.conf) — missing A52s firmware inputs.
- [`FINAL_STATUS.md`](../../reports/FINAL_STATUS.md) — recorded work and current blockers.
