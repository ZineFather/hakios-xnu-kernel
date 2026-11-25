# Storage safety audit

This report is host-side only. It scans source text and records findings; it does not contact a phone. The categories are deliberately separate:

1. **Host-side write** — permitted (reports, manifests, build output).
2. **Device-side RAM operation** — permitted (`fastboot boot`, read-only log fetch).
3. **Device-side persistent write** — forbidden.

## Scope

- Package: `<previous-package-root>`
- Kernel checkout: `<previous-temp>\kernel-src`

## Summary

| Scope | Host-side | RAM-only | Persistent | Unmitigated persistent |
| --- | ---: | ---: | ---: | ---: |
| Porting package | 8 | 26 | 9 | 0 |
| Upstream kernel checkout | 394 | 13 | 215 | 7 |

## Package persistent-write findings

| File:line | Severity | What | Mitigation |
| --- | --- | --- | --- |
| `<previous-package-root>\hakiosport\build.py:7` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `<previous-package-root>\hakiosport\build.py:15` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `<previous-package-root>\hakiosport\build.py:438` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `<previous-package-root>\hakiosport\image.py:21` | warning | enables writes to the port's own 'darwin' partition | the boot-argument policy rejects ufs_write=1 and the port has no darwin partition |
| `<previous-package-root>\hakiosport\image.py:22` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `<previous-package-root>\hakiosport\image.py:23` | warning | keeps /private/var on the phone's storage | the boot-argument policy rejects var_store=1 and var_hfs= |
| `<previous-package-root>\hakiosport\portgen.py:146` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `<previous-package-root>\tools\storage_safety_report.py:147` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |
| `<previous-package-root>\tools\storage_safety_report.py:184` | critical | the upstream loader writes its log to this partition after every run | loader built with -DHAKIOS_NO_PERSISTENT_LOG=1 (patches/0001-loader-no-persistent-log.patch); the log stays in RAM for fastboot get_staged |

## Upstream persistent-write findings

The checkout contains **215** persistent-write hits. The unmitigated ones are listed below; the full list is in the JSON report. These are source findings, not proof that a boot path runs them.

| File:line | Severity | What | Mitigation |
| --- | --- | --- | --- |
| `<previous-temp>\kernel-src\arch\arm64\boot\dts\_template\board.dts:78` | critical | filesystem or partition table write | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:178` | critical | raw block write | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:227` | critical | raw block write | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:256` | critical | raw block write | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:271` | critical | writes the device or changes its privilege state | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:294` | critical | raw block write | **NONE** |
| `<previous-temp>\kernel-src\darwin\tools\darwin-write.py:326` | critical | raw block write | **NONE** |

## Loader log check

Upstream HakiOS's loader writes its log to a GPT partition named `logdump` by default. The build path for this project passes `LOADER_CFLAGS=-DHAKIOS_NO_PERSISTENT_LOG=1`; the source-level equivalent is `patches/0001-loader-no-persistent-log.patch`. The log remains in RAM for a read-only `fastboot get_staged` fetch.

- Loader source guard: **PASS** — the loader source contains the HAKIOS_NO_PERSISTENT_LOG guard
- Loader binary: **not checked** (no built `loader.efi`).

## Command log

- Result: **PASS**
- <previous-package-root>\logs\device-commands.jsonl not found: no device commands were recorded

## Verdict

The porting package itself contains no unmitigated persistent-write path. Every `logdump`/write-enabling hit it contains is guarded by the loader flag or rejected by the boot-argument policy.
The upstream checkout still contains unmitigated write code in developer tools and templates. Those tools are not part of this boot workflow and must not be run. This scan is **not a pass for the whole upstream tree**.

**Automatic boot remains blocked independently of this audit:** the Samsung Galaxy A52s 5G bootloader does not provide Fastboot, so the only permitted boot operation cannot be issued. This tool will not substitute flashing or Odin.

## Safety conclusion

- Persistent device storage was **not modified**: no device was connected and no device command was issued.
- No boot image was generated.
- No evidence exists that the port boots or that any driver works on this phone.
