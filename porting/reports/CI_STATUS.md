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
| Latest run | [45471518494](https://github.com/ZineFather/hakios-xnu-kernel/actions/runs/45471518494) — **success** |

## Commits on `a52sxq-port`

| Commit | Purpose |
| --- | --- |
| `3924c52` | Add the a52sxq port package, `porting/hakios_port.py`, 52 host tests, the loader guard and the CI workflow. |
| `e96cdd1` | Fix the `inspect` test: a read-only adb probe may be recorded on hosts that ship adb; assert policy compliance and no boot/write verb instead. |
| `a6b070f` | Fix two relative links so the repository link check is not broken by this port. |
| `HEAD` | CI status report (this file) and the matching report updates. |

## Workflow jobs

| Job | Runner | Result | What it did |
| --- | --- | --- | --- |
| `checks` | `ubuntu-24.04` | **success** (9–18 s) | Ran the 52 host tests, imported the device package with `tools/device.py add`, ran `tools/boards.py check` and `tools/boards.py status a52sxq`, ran `hakios_port.py verify-safety`, and asserted the audit passed. |
| `loader` | `ubuntu-24.04` | **success** (21–52 s) | Installed `clang`/`lld`, imported the package, built `arch/arm64/boot/loader.efi` with `LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1`, and ran `porting/tools/check_built_loader.py` (source guard + ASCII/UTF-16LE check). |
| `kernel` | `macos-14` | **skipped** (opt-in) | Runs only when repository variable `HAKIOS_BUILD_KERNEL=true`. It was not set, so no kernel was built and no success is claimed. |

## Artifacts from run 45471518494

| Artifact | Size (zip) | Expires | Contents |
| --- | ---: | --- | --- |
| `a52sxq-audit` | 45,728 bytes | 2026-12-08 | The audit reports written in CI. |
| `a52sxq-loader` | 37,663 bytes | 2026-12-08 | `loader.efi` (76,800 bytes uncompressed). |

The loader artifact was downloaded and inspected on the local host:

```
bytes: 76800
dos magic: b'MZ'
pe offset: 0x78 signature: b'PE\x00\x00'
machine: 0xaa64 (AArch64 PE)
loader check: PASS - contains no logdump string
```

So a real AArch64 UEFI loader was built, and the RAM-only log guard is present in the
built binary. This is a **build** result: it is not a phone boot, and it says nothing
about any driver.

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
  is a person running `fastboot boot <image>` at the phone, and no job does that.
- The audit step fails the build if any unmitigated persistent write appears in the
  porting package or if the command log contains a refused command.
- The loader check fails the build if the built binary carries the persistent log
  partition name in ASCII or UTF-16LE.
- Heavy compilation happens on GitHub's runners, not on the low-resource local host.
