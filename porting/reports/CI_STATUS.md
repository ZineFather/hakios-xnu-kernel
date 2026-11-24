# CI status — public fork and GitHub Actions

**Everything below was executed on GitHub's runners. No phone was contacted and no device
command was issued by any job.**

## Fork

| Item | Value |
| --- | --- |
| Upstream | <https://github.com/oosexgang/hakios-xnu-kernel> (branch `common`) |
| Public fork | <https://github.com/ZineFather/hakios-xnu-kernel> |
| Visibility | **PUBLIC** (`gh repo view --json visibility` → `PUBLIC`) |
| Port branch | `a52sxq-port` |
| Workflow | `.github/workflows/build-a52sxq.yml` |
| Latest run | [45489633569](https://github.com/ZineFather/hakios-xnu-kernel/actions/runs/45489633569) — **success**, all three jobs |
| Kernel job | `kernel and loader` — **success** in 11 m 38 s (macOS Intel runner) |
| Artifacts | `a52sxq-audit`, `a52sxq-loader`, `a52sxq-kernel` |

## Commits on `a52sxq-port`

| Commit | Purpose |
| --- | --- |
| `3924c52` | Add the a52sxq port package, `porting/hakios_port.py`, 52 host tests, the loader guard and the CI workflow. |
| `e96cdd1` | Fix the `inspect` test: a read-only adb probe may be recorded on hosts that ship adb; assert policy compliance and no boot/write verb instead. |
| `a6b070f` | Fix two relative links so the repository link check is not broken by this port. |
| `4cc4159` | Add this report; record the green run and the built loader. |
| `5bd3d97`, `0bdaf71` | Report wording (no moving "latest" label). |
| `44236be` | CI: build the kernel on GitHub by default (opt-out with `HAKIOS_BUILD_KERNEL=false`). |
| `9622685` | CI: macOS runner label `macos-15` (the arm64 pool later proved unavailable to this repository). |
| `3874205` | CI: install the autotools that `kernel/deps/stage1.sh` checks for. |
| `3a5e001` | CI: run the kernel job on the Intel macOS pool; the arm64 pool never acquired the job. |
| `065c095` | CI: install `gawk`, which `kernel/build.sh` requires by name. |
| `efd2b16` | CI: install LLVM `lld` for the loader link (`lld-link`). |
| `7455291` | CI: build the kernel and the loader, not an image the board cannot describe. |

## Workflow jobs (run 45489633569)

| Job | Runner | Result | What it did |
| --- | --- | --- | --- |
| `checks` | `ubuntu-24.04` | **success** (18 s) | 52 host tests, `tools/device.py add a52sxq`, `tools/boards.py check` and `status a52sxq`, `hakios_port.py verify-safety`, and an assertion that the audit passed. |
| `loader` | `ubuntu-24.04` | **success** (58 s) | `clang`/`lld`, package import, `arch/arm64/boot/loader.efi` built with `LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1`, then `porting/tools/check_built_loader.py` (source guard + ASCII/UTF-16LE check). |
| `kernel and loader` | `macos-15-intel` | **success** (11 m 38 s) | Homebrew `automake autoconf libtool gawk lld`, package import, `make kernel` (Apple's XNU 12377.121.6 sources + HakiOS overlay, `MACHINE=BCM2837`), `make loader` with the RAM-only log guard, the built-loader check, and an artifact with both binaries. |

The kernel job is **on by default**: its condition is `vars.HAKIOS_BUILD_KERNEL != 'false'`,
so it runs on every push unless the repository variable is explicitly set to `false`.
Evidence from the workflow runs before this one, kept here because it shaped the job:

- `macos-14`: rejected at dispatch — "The configuration 'macos-14-arm64-us-default' is not supported".
- `macos-15` (arm64): failed twice without ever starting — "The job was not acquired by Runner
  of type hosted even after multiple attempts" (15 minutes queued, then cancelled).
- `macos-15-intel`: acquired in seconds and built the kernel.
- Missing host tools, found in order and fixed: `autoconf`/`automake` (stage1 check), `gawk`
  (`kernel/build.sh` looks for it by name), `lld-link` (the loader is a PE image).

## Artifacts from run 45489633569

| Artifact | Size (zip) | Expires | Contents |
| --- | ---: | --- | --- |
| `a52sxq-audit` | 48,591 bytes | 2026-12-08 | The audit reports written in CI. |
| `a52sxq-loader` | 37,663 bytes | 2026-12-08 | `loader.efi` from the Ubuntu job. |
| `a52sxq-kernel` | 6,940,846 bytes | 2026-12-08 | `mach.development.bcm2837` (19,991,736 bytes) and `loader.efi` (76,800 bytes). |

The kernel artifact was downloaded and inspected on the local host:

```
kernel bytes: 19991736
kernel magic: cffaedfe (64-bit Mach-O, little endian)
kernel cputype: 0x100000c (0x0100000c = ARM64)
kernel knows a52sxq: True
kernel knows qemu-virt: True
loader bytes: 76800
dos: b'MZ'
pe signature: b'PE\x00\x00' machine: 0xaa64
loader knows a52sxq: False
loader log check: PASS - contains no logdump string
```

So a real ARM64 XNU kernel and a real AArch64 UEFI loader were built on GitHub's runner, and
the kernel's board table contains `a52sxq`. These are **build** results: nothing was started
on a phone, and they say nothing about any driver.

## Why there is no `a52sxq-image` artifact yet

`tools/image.py build` refuses with:

```
arch/arm64/boot/loader.efi does not know a52sxq: it was built before the package was here.
```

The loader's `platforms.h` lists only boards that have a `loader { }` section
(`tools/boards.py`, "platforms.h: the loader's description of every board with a [loader]
section"), and `arch/arm64/boot/dts/a52sxq/board.dts` has none. That section carries the
phone's own loader platform description — framebuffer base, payload base and the rest — and
none of it has been read from this phone: it was never connected, and its Samsung
Download/Odin bootloader offers no fastboot entry. The values were therefore not invented;
the image step is left out instead. The reference package `sm7325-device` in this checkout
(POCO X5 Pro 5G / redwood, the same SoC) shows what a filled-in section looks like; its
values are that phone's and were measured on it, not on an A52s 5G.

The loader is also built with a **placeholder identity**:

```
build.sh: no iPhone device tree (.../ios27/DeviceTree.bin): the loader is built with a
placeholder identity, and Darwin will not start
```

That is expected without an Apple IPSW; the loader binary and its RAM-only log are real, but
starting Darwin needs the identity of the iPhone the system image belongs to
(`Documentation/darwin26-boot.md`).

## Upstream `check` job

The fork's inherited `check` workflow still fails. Every remaining hit is a pre-existing
upstream documentation reference to `arch/arm64/boot/uefi/`, which is not in this
upstream commit:

```
Documentation/architecture.md:184: `arch/arm64/boot/uefi/` is not in the repository
Documentation/porting.md:91-93:   `arch/arm64/boot/uefi/` is not in the repository
arch/arm64/boot/README.md:108:    `arch/arm64/boot/uefi/` is not in the repository
```

No `porting/` path appears in the failure after `a6b070f`. This report does **not** claim
the whole fork passes the upstream check; it claims the a52sxq workflow passes.

## Safety

- No job contains a device write command; the only device operation the project permits
  is a person running `fastboot boot <image>` at the phone, and no job does that. The
  workflow contains no `fastboot` invocation at all.
- The kernel and loader are built with `-DHAKIOS_NO_PERSISTENT_LOG=1`, and the loader check
  fails the build if the binary carries the persistent log partition name in ASCII or
  UTF-16LE.
- The audit step fails the build if any unmitigated persistent write appears in the
  porting package or if the command log contains a refused command.
- Heavy compilation happens on GitHub's runners, not on the low-resource local host.
