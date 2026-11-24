# Storage-write audit

Scope: every source and script reachable by this porting workflow. The three categories are kept apart on purpose: host-side file writes are permitted; device-side RAM operations are permitted; device-side persistent writes are forbidden.

## Scanned

- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq`

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
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\build.py:7` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\build.py:15` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\build.py:438` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\image.py:21` | warning | enables writes to the port's own 'darwin' partition | the boot-argument policy rejects ufs_write=1 and the port has no darwin partition |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\image.py:22` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\image.py:23` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\portgen.py:146` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\tools\storage_safety_report.py:147` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\tools\storage_safety_report.py:184` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |

## Device RAM operations (permitted)

- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\devices\a52sxq\build.sh:6` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:11` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:404` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:405` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:418` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:545` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:604` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\boot.py:606` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\build.py:337` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\cli.py:7` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\cli.py:298` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\devices.py:80` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\devices.py:98` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\devices.py:238` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\devices.py:268` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\devices.py:277` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\fastboot.py:95` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\fastboot.py:98` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\portgen.py:93` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\portgen.py:118` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\portgen.py:147` — reads the loader log from RAM to the host
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\report.py:118` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\report.py:121` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\hakiosport\runner.py:87` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\tools\storage_safety_report.py:85` — starts an image from RAM; writes nothing
- `C:\Users\claymi5433\Documents\Default Project\hakios-a52sxq\tools\storage_safety_report.py:151` — reads the loader log from RAM to the host

## Host-side writes (permitted)

8 hit(s): report files, manifests and build output on this computer.
