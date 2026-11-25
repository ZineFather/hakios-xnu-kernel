# Storage-write audit

Scope: every source and script reachable by this porting workflow. The three categories are kept apart on purpose: host-side file writes are permitted; device-side RAM operations are permitted; device-side persistent writes are forbidden.

## Scanned

- porting

## Summary

| Category | Hits |
| --- | --- |
| host-side write | 8 |
| device-side RAM operation | 26 |
| device-side persistent write | 9 |
| tooling/documentation | 0 |

**No unmitigated persistent-write path found in the scanned boot workflow.** Upstream HakiOS does write `logdump` by default; the loader build for this project removes that write. When a kernel checkout and a built loader are supplied, `verify-safety` also checks the source guard and the binary; those results are reported separately below.

## Persistent-write findings

| File:line | Severity | What | Mitigation |
| --- | --- | --- | --- |
| `porting/hakiosport/build.py:7` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `porting/hakiosport/build.py:15` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `porting/hakiosport/build.py:440` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `porting/hakiosport/image.py:21` | warning | enables writes to the port's own 'darwin' partition | the boot-argument policy rejects ufs_write=1 and the port has no darwin partition |
| `porting/hakiosport/image.py:22` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `porting/hakiosport/image.py:23` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `porting/hakiosport/portgen.py:146` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `porting/tools/storage_safety_report.py:147` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `porting/tools/storage_safety_report.py:184` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |

## Device RAM operations (permitted)

- `porting/devices/a52sxq/build.sh:6` — starts an image from RAM; writes nothing
- `porting/hakiosport/boot.py:11` — starts an image from RAM; writes nothing
- `porting/hakiosport/boot.py:424` — starts an image from RAM; writes nothing
- `porting/hakiosport/boot.py:425` — starts an image from RAM; writes nothing
- `porting/hakiosport/boot.py:438` — starts an image from RAM; writes nothing
- `porting/hakiosport/boot.py:565` — reads the loader log from RAM to the host
- `porting/hakiosport/boot.py:624` — reads the loader log from RAM to the host
- `porting/hakiosport/boot.py:626` — reads the loader log from RAM to the host
- `porting/hakiosport/build.py:337` — starts an image from RAM; writes nothing
- `porting/hakiosport/cli.py:7` — starts an image from RAM; writes nothing
- `porting/hakiosport/cli.py:298` — starts an image from RAM; writes nothing
- `porting/hakiosport/devices.py:85` — starts an image from RAM; writes nothing
- `porting/hakiosport/devices.py:105` — starts an image from RAM; writes nothing
- `porting/hakiosport/devices.py:249` — starts an image from RAM; writes nothing
- `porting/hakiosport/devices.py:290` — starts an image from RAM; writes nothing
- `porting/hakiosport/devices.py:300` — starts an image from RAM; writes nothing
- `porting/hakiosport/fastboot.py:95` — reads the loader log from RAM to the host
- `porting/hakiosport/fastboot.py:98` — reads the loader log from RAM to the host
- `porting/hakiosport/portgen.py:93` — starts an image from RAM; writes nothing
- `porting/hakiosport/portgen.py:118` — starts an image from RAM; writes nothing
- `porting/hakiosport/portgen.py:147` — reads the loader log from RAM to the host
- `porting/hakiosport/report.py:118` — starts an image from RAM; writes nothing
- `porting/hakiosport/report.py:121` — starts an image from RAM; writes nothing
- `porting/hakiosport/runner.py:87` — starts an image from RAM; writes nothing
- `porting/tools/storage_safety_report.py:85` — starts an image from RAM; writes nothing
- `porting/tools/storage_safety_report.py:151` — reads the loader log from RAM to the host

## Host-side writes (permitted)

8 hit(s): report files, manifests and build output on this computer.
