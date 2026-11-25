# HakiOS porting tool — Samsung Galaxy A52s 5G (`a52sxq`)

> # ⚠ NOT BOOTED / NOT SUPPORTED ON HARDWARE
>
> **No boot image was generated. No boot was attempted. No device was connected. No persistent device storage was modified. The port is NOT claimed to work on hardware.**
>
> The Samsung Galaxy A52s 5G (SM-A528B, `a52sxq`, Snapdragon 778G / SM7325) uses Samsung Download/Odin, **not fastboot**. HakiOS's only entry path is `fastboot boot`. The `boot` command therefore refuses with exit code **3** and there is **no flashing fallback**. The bootloader is already unlocked — never unlock it.

## Purpose

This package provides `hakios_port.py`, a host-side tool to inspect a caller-selected device, generate a HakiOS device package, plan a host build, attempt **one RAM-only** `fastboot boot` of an existing local image (only on devices that actually support it), collect the temporary boot log, return to stock Android, and audit the whole workflow for persistent-write paths.

The device is a **query**, not a hard-coded global: use `--device NAME` (human name/model) or `--codename CODE`. Generic code contains no phone name; device facts live in the registry and in `devices/<codename>/`.

## Safety policy (absolute storage safety)

Every adb/fastboot invocation goes through a default-deny command policy **before** a process is spawned:

- **Allowed fastboot verbs:** `devices`, `getvar <read-only name>`, `boot <existing local file>`, `reboot`, `get_staged <host file>`, `version`.
- **Allowed adb:** `devices`, `version`, `get-state`, read-only `shell`/`exec-out` commands, `pull` from read-only roots, and `reboot`.
- **Refused, always:** `flash`, `flashall`, `erase`, `format`, `set_active`, `partition`, `resize`, `wipe`, `oem`/`flashing` lock or unlock, `-w`, adb `push`/`root`/`remount`/`sideload`/`install`, root writes, bootloader-state changes, and shell metacharacter injection.
- `fastboot boot` requires **exactly one argument that is an existing, non-empty local regular file**; partition-looking names and missing files are refused.
- No Odin path, no flashing workaround, no unlock command exists anywhere in the tool. The boot gate checks capability before identity, identity before image inspection, and image inspection before any boot command.
- Write-enabling boot arguments (`ufs_write=1`, `var_store=1`, `var_hfs=`, `root_apfs=`, `dsu_write=`) cause a refusal.
- All file writes are **host-side** (reports, logs, generated packages, build output). The only device-side operation that starts code is `fastboot boot`, which writes nothing.

Upstream HakiOS's loader writes its log to a `logdump` partition after every run. The build passes `LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1` to the loader build, which removes that write; the log stays in RAM and can be fetched with `fastboot get_staged`. After a real build, the tool **checks the built loader binary** for both ASCII and UTF-16LE `logdump` strings and refuses to use it if either is present. `patches/0001-loader-no-persistent-log.patch` is the source-level equivalent (its `git apply --check` passed: 16 insertions, one file). No loader was built here, so the binary check has not been exercised.

## Confirmed blocker and evidence

| Question | Answer |
| --- | --- |
| Can `a52sxq` run `fastboot boot`? | **NO** |
| Bootloader kind | `samsung-download` (Samsung Download / Odin protocol) |
| Documented fastboot boot | `False` |
| Fallback | **None.** No flashing, Odin, TWRP boot-partition write, slot change or unlock substitution. |

Evidence:

- LineageOS's [a52sxq install guide](https://wiki.lineageos.org/devices/a52sxq/install/) writes every image in Download mode with samloader (Odin protocol) and has no fastboot step.
- HakiOS's only entry path is `fastboot boot` (see its `arch/arm64/boot/README.md`).
- The supplied z3q TWRP path uses `dd` to replace `/dev/block/by-name/boot`, so it is not a RAM-only alternative; see [`Z3Q_REFERENCE.md`](reports/Z3Q_REFERENCE.md).
- A unit test confirms the device stays unsupported even if a fastboot device is present.

The SoC layer in `devices/a52sxq/soc.dtsi` is the SM7325 layer from HakiOS's official `redwood` package (same SoC). The phone-specific `board.dts` is deliberately empty of unverified addresses and features. This is a structural starting point, not a claim that any driver works.

## Public fork and CI

The official upstream repository is <https://github.com/oosexgang/hakios-xnu-kernel> (branch `common`).
A public fork holds the `a52sxq` port branch and the CI workflow:
<https://github.com/ZineFather/hakios-xnu-kernel> (`a52sxq-port`).

| Item | Detail |
| --- | --- |
| Fork visibility | **PUBLIC** (verified with `gh repo view --json visibility`) |
| Branch | `a52sxq-port` |
| Workflow | `.github/workflows/build-a52sxq.yml` |
| Jobs | `checks` (package + tool tests + audit), `loader` (real UEFI loader build and RAM-only log check), `kernel and loader` (ARM64 XNU kernel + AArch64 loader on a macOS runner, on by default; `HAKIOS_BUILD_KERNEL=false` opts out) |
| Phone use | none — CI never contacts a phone and contains no device command |

The fork branch commits the imported package at `arch/arm64/boot/dts/a52sxq/`, the porting
tool at `porting/`, and the loader source guard, so the heavy work runs on GitHub's runners
instead of a low-resource local machine. Artifacts are temporary (14 days) and are only
build outputs; none is a phone image.

## Install

### Arch Linux / CachyOS (recommended native build host)

```sh
sudo pacman -S clang lld make git python android-tools
```

`python` on Arch provides `python3`, which the HakiOS build scripts call. Obtain the HakiOS kernel checkout separately (`git clone -b common https://github.com/oosexgang/hakios-xnu-kernel`) and pass it with `--kernel-src DIR` or set `HAKIOS_KERNEL`; a real build also needs a phone-specific UEFI build and a `uefi { }` section in `board.dts`.

### Windows — use WSL2

Native Windows cannot run HakiOS's bash + GNU make + clang/lld-link builds. Inspect, port, audit and reporting work natively, but builds must run in WSL2.

```powershell
# Elevated PowerShell on Windows:
wsl --install -d Ubuntu
```

```sh
# Inside the WSL2 Ubuntu shell:
sudo apt update
sudo apt install -y clang lld make git python3 adb fastboot
```

For an Arch-family distro inside WSL2, use the pacman command above. Run `hakios_port.py` from the package root inside WSL2; do not use Odin or any write command as a workaround.

## Run

From the package root:

```sh
cd hakios-a52sxq
```

The seven commands, with example invocations:

```sh
# 1. Read-only hardware inspection; a missing device is reported honestly.
python3 hakios_port.py --codename a52sxq inspect

# 2. Generate/refresh the device package without clobbering local edits.
python3 hakios_port.py --codename a52sxq port

# 3. Plan the host build without executing anything.
python3 hakios_port.py --codename a52sxq build --dry-run

# 4. Attempt a RAM-only boot of an existing local image.
#    On a52sxq this ALWAYS refuses (exit 3); --image and --yes do not override the gate.
python3 hakios_port.py --codename a52sxq boot --dry-run --image build/images/a52sxq/boot.img

# 5. Poll read-only loader queries and stage the RAM log onto the host.
python3 hakios_port.py --codename a52sxq monitor --dry-run

# 6. Return to stock Android (ordinary reboot) and print recovery steps.
python3 hakios_port.py --codename a52sxq reboot --dry-run

# 7. Audit sources, patch guard, loader binary and the device-command log.
python3 hakios_port.py --codename a52sxq verify-safety
```

To supply a checkout for a real build or a pointed audit, add `--kernel-src /path/to/hakios-xnu-kernel` to `build` or `verify-safety`. Global options may be placed before or after the subcommand. Select the device by name instead of codename:

```sh
python3 hakios_port.py --device "Samsung Galaxy A52s 5G" boot --dry-run
```

Use `--serial` when more than one device is attached, `--reports-dir` / `--audit-log` to relocate host outputs, and `--force` only if you intentionally want to overwrite locally modified generated port files.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Command completed (a dry run or an honest "no device" report can be a successful run). |
| 1 | Unclassified error. |
| 2 | Usage error: bad arguments, missing tool, or nothing to operate on. |
| 3 | Unsupported hardware — e.g. no fastboot protocol. Never work around this by flashing. |
| 4 | Policy violation: a forbidden device command or write-enabling image was refused before execution. |
| 5 | Build blocked: unsupported host, missing toolchain/sources, or a failed build step. |
| 6 | Boot failed after a boot was actually attempted. |
| 7 | Storage-write audit failed (unmitigated write path, bad loader, or an invalid recorded device command). A missing command log is not a failure: it means no device command was issued. |
| 130 | Interrupted by the user. |

## Directory layout

```
hakios-a52sxq/
├── hakios_port.py               # entry point
├── hakiosport/                  # cli, policy, devices, boot, build, audit, image,
│                                # inspect, portgen, report, runner, adb, fastboot, errors
├── devices/a52sxq/              # board.dts, soc.dtsi, device.conf, README.md,
│                                # BUILDING.md, COMPATIBILITY.md, DRIVERS.md, DT_NOTES.md,
│                                # firmware.conf, build.sh, configs/
├── patches/                     # 0001-loader-no-persistent-log.patch, README.md
├── tools/                       # storage_safety_report.py, check_built_loader.py
├── tests/                       # run_tests.py, test_*.py, fixtures.py
├── reports/                     # generated + hand-written reports (see REPORT_INDEX.md)
└── logs/                        # device-command JSON Lines audit log, written only when
                                 # a device command is issued (empty on this host)
```

## Tests

```sh
python3 tests/run_tests.py
```

The suite runs from any directory. The latest local run passed **58 host-side tests**: refusal tests, policy checks, image checks, audit classification, idempotent port generation, device-package integrity and CLI smoke tests. Passing these checks does not establish hardware compatibility.

## Current status (honest)

- `hakios_port.py --help` exits 0; seven subcommands are listed.
- `inspect` exits 0 and writes an honest report: no adb device was inspected; adb and fastboot are not installed on this host. It writes both the generic `hardware.md` / `hardware.json` and the device-named `a52sxq_hardware_report.md` / `.json`.
- `port` exits 0; generation is idempotent and local edits are skipped; structural checks pass.
- `build --dry-run` exits 0, records blockers (Windows host, no kernel checkout, no `clang`/`lld-link`/`python3`/`make`) and executes nothing.
- `boot --dry-run` exits **3**: no fastboot protocol; no device command was issued.
- `verify-safety` exits **0** on this host: 43 findings, 0 unmitigated persistent writes, `command log=PASS` with the note "no device commands were recorded" (no log exists because no device command was issued). `patch=not checked` and `loader=not checked` because no kernel checkout or built loader was supplied — this is a host-side audit result, **not** a hardware pass.
- `tools/storage_safety_report.py --kernel-src ...` records the package plus the temporary upstream checkout: the package has 0 unmitigated writes and the loader source guard PASSes after applying the patch; the upstream tree still has **7 unmitigated developer-tool/template writes**, so the whole upstream tree is **not** write-free.
- `git apply --check` passed for `patches/0001-loader-no-persistent-log.patch`; the patch was then applied to the temporary checkout. The local Windows host cannot build, so the binary check was exercised in CI instead: GitHub Actions built `loader.efi` (76,800 bytes, AArch64 PE) and the downloaded artifact contains no persistent-log partition string.
- **GitHub Actions:** the verified `a52sxq` workflow run [45519914845](https://github.com/ZineFather/hakios-xnu-kernel/actions/runs/45519914845), for port source commit `261db29`, passed all three jobs: package/tool checks, the loader RAM-log check, and the kernel/loader build. It published `a52sxq-kernel`, `a52sxq-loader` and `a52sxq-audit` artifacts. The kernel job runs by default; `HAKIOS_BUILD_KERNEL=false` opts out. No image is built: the board has no verified `loader { }` section, so image generation must wait for A52s-specific platform values. The separate inherited `check` workflow remains red on repository-wide checks; known failures are tracked in `reports/CI_STATUS.md`.
- **No phone boot image was built; no boot was attempted; no device was connected; no hardware was tested.** `reports/` contains the full record; start with `reports/REPORT_INDEX.md`, `reports/FINAL_STATUS.md` and `reports/CI_STATUS.md`.

## Recovery instructions

Return to stock Android without changing storage:

1. If the phone is running a test image or is in a bootloader menu, hold Power for 10–15 seconds until it restarts, or choose the stock bootloader's normal boot / "Restart bootloader" option.
2. If it is in Samsung Download (Odin) mode, **do not connect Odin**: leave Download mode with the normal boot / restart option, or hold Power until the phone restarts.
3. Let the stock bootloader start Android normally; nothing needs to be re-flashed.
4. In short: **do not flash anything**; a normal reboot preserves the original Android installation.

The tool never unlocks the bootloader, never flashes or erases partitions, never changes active slots, and never writes to the phone's storage. If the phone does not come back, stop and use the stock bootloader or recovery menu rather than substituting an Odin flash for a reboot.
