# Loader patch: no persistent log

## Why it exists

Upstream HakiOS's loader looks up a GPT partition named `logdump` and raw-writes
the composed loader/kernel log to it **after every run**. That is a persistent
storage write, and the A52s port's safety rule forbids any such write: the only
permitted boot action is a RAM boot (`fastboot boot`), and this phone does not
even have fastboot (it uses Samsung Download/Odin), so the tool refuses to boot
it at all.

`0001-loader-no-persistent-log.patch` adds a compile-time guard to
`arch/arm64/boot/src/logstore.c` in the upstream `common` checkout:

* with `HAKIOS_NO_PERSISTENT_LOG` defined, neither the partition lookup nor the
  block write (nor the ASCII/UTF-16 `logdump` strings) is compiled in;
* `compose_logs()` still fills `out_buf`, `staged_data` and `staged_len`, so the
  log stays in RAM and the host can still fetch it with `fastboot get_staged`;
* a short line says the log is kept in RAM only;
* without the define, the old write path is untouched, so the patch is suitable
  for upstream use.

## How the port uses it

The port's build passes `-DHAKIOS_NO_PERSISTENT_LOG=1` through the loader
build's `LOADER_CFLAGS` environment variable (`make loader` honours that
variable). That is the normal route: no source file in the upstream checkout
has to be edited.

This patch is the **source-level equivalent** for people who prefer to patch
the checkout instead of relying on the build flag. It applies to the exact
`common` checkout used by this port; it does not change any other file.

## Verification

`hakiosport/audit.py` inspects a **built** loader binary and rejects it if
either the ASCII bytes `logdump` or the UTF-16LE bytes for `logdump` appear in
it. It also checks that the loader source carries the
`HAKIOS_NO_PERSISTENT_LOG` guard.

On this host the patch was checked with `git apply --check` against the clean
upstream checkout, and applied to a temporary clone where the repository's
Python files passed `py_compile`/`compileall`. **No loader binary was built on
this host** (there is no AArch64 cross-compiler here), so the binary check has
not been run and no boot or device test was performed.
