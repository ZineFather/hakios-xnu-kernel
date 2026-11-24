"""The device-command policy: the one place that decides what may be sent to a phone.

Every adb and fastboot invocation in this project goes through :func:`check_fastboot`
or :func:`check_adb`.  The functions raise :class:`PolicyViolation` *before* a
process is spawned, so a forbidden verb cannot reach a device even if a caller
passes it by mistake.

Design rules
------------
* Default deny.  A fastboot verb that is not on the explicit allow-list is refused,
  so a new fastboot feature cannot silently become reachable.
* ``fastboot boot`` is the only verb that starts an image.  It is accepted only with
  exactly one argument, and that argument must be an existing local regular file.
  Partition syntax (``boot:foo``) and block-device-looking paths are refused.
* Anything that changes persistent device state is refused outright, including
  ``flash``, ``erase``, ``format``, ``set_active``, ``partition``, ``oem``/``flashing``
  lock or unlock, and ``-w``.
* ``adb shell`` is parsed, not trusted: shell metacharacters, redirections and
  pipes are refused, then the command is checked against a read-only allow-list.

The policy is intentionally independent of any particular device.  Device-specific
knowledge lives in :mod:`hakiosport.devices`.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Iterable, Sequence

from .errors import PolicyViolation

# --------------------------------------------------------------------------- #
# fastboot
# --------------------------------------------------------------------------- #

#: Verbs that are allowed at all.  Everything else is refused by default.
ALLOWED_FASTBOOT_VERBS = frozenset(
    {
        "devices",
        "getvar",
        "boot",
        "reboot",
        "get_staged",
        "fetch",
        "version",
        "--version",
    }
)

#: Tokens that must never appear anywhere in a fastboot command line.  This is a
#: second, belt-and-braces check on top of the allow-list: it also catches a verb
#: smuggled in after a global option.
FORBIDDEN_FASTBOOT_TOKENS = frozenset(
    {
        "flash",
        "flashall",
        "flashall:",
        "erase",
        "format",
        "format:",
        "set_active",
        "set-active",
        "--set-active",
        "partition",
        "resize",
        "create-logical-partition",
        "delete-logical-partition",
        "snapshot-update",
        "wipe-super",
        "wipe",
        "unlock",
        "lock",
        "oem",
        "flashing",
        "flash:raw",
        "update",
        "sideload",
        "-w",
        "--wipe",
        "reboot-bootloader",
    }
)

#: ``getvar`` names that are read-only.  ``all`` is the standard dump.
READ_ONLY_GETVARS = frozenset(
    {
        "all",
        "product",
        "unlocked",
        "current-slot",
        "slot-count",
        "slot-successful:a",
        "slot-successful:b",
        "slot-unbootable:a",
        "slot-unbootable:b",
        "version",
        "version-bootloader",
        "version-baseband",
        "serialno",
        "secure",
        "variant",
        "max-download-size",
        "is-userspace",
        "battery-voltage",
        "battery-soc-ok",
        "hw-revision",
        "cpu-var",
        "off-mode-charge",
    }
)

#: A path that looks like a partition rather than a file (``boot``, ``boot_a``).
_PARTITION_LIKE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _looks_like_local_file(value: str) -> bool:
    """True when ``value`` is a path to an existing, non-empty regular file.

    ``fastboot boot`` is only ever given a file.  Requiring existence here means a
    typo such as ``fastboot boot boot`` cannot be interpreted by the bootloader as
    a partition name.
    """

    if not value or value.startswith("-"):
        return False
    try:
        path = Path(value).expanduser()
    except OSError:
        return False
    # A Windows drive letter contains ':' but is still a local path; only a colon
    # elsewhere means fastboot's ``boot:partition`` / ``flash:raw`` syntax.
    remainder = value[len(path.drive) :] if path.drive else value
    if ":" in remainder:
        return False
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def check_fastboot(argv: Sequence[str], *, allow_remote_fetch: bool = False) -> list[str]:
    """Validate a fastboot argument vector (without the ``fastboot`` executable).

    Returns the vector unchanged on success; raises :class:`PolicyViolation`
    otherwise.  The caller must use the returned vector.
    """

    args = [str(a) for a in argv]
    if not args:
        raise PolicyViolation("empty fastboot command")

    lowered = [a.lower() for a in args]

    # Global options are only tolerated in the two harmless forms we use.
    while lowered and lowered[0].startswith("-") and lowered[0] not in {"--version"}:
        # ``-s SERIAL`` is the only global option accepted, and only with a value.
        if lowered[0] == "-s" and len(args) >= 3:
            args = args[2:]
            lowered = lowered[2:]
            continue
        raise PolicyViolation(f"fastboot option not allowed: {args[0]}")

    if not args:
        raise PolicyViolation("empty fastboot command after global options")

    verb = lowered[0]

    # Belt and braces: no forbidden token anywhere on the line.
    for token in lowered:
        if token in FORBIDDEN_FASTBOOT_TOKENS:
            raise PolicyViolation(
                f"fastboot {token!r} is forbidden: this tool only ever runs "
                "'fastboot boot <temporary image>' and read-only queries"
            )

    if verb not in ALLOWED_FASTBOOT_VERBS:
        raise PolicyViolation(
            f"fastboot verb {verb!r} is not on the allow-list "
            f"({', '.join(sorted(ALLOWED_FASTBOOT_VERBS))})"
        )

    if verb in {"devices", "version", "--version"}:
        if len(args) != 1:
            raise PolicyViolation(f"fastboot {verb} takes no arguments")
        return args

    if verb == "getvar":
        if len(args) != 2:
            raise PolicyViolation("fastboot getvar takes exactly one name")
        name = args[1].lower()
        if name not in READ_ONLY_GETVARS:
            raise PolicyViolation(
                f"fastboot getvar {args[1]!r} is not a known read-only variable"
            )
        return args

    if verb == "boot":
        if len(args) != 2:
            raise PolicyViolation(
                "fastboot boot takes exactly one temporary image and nothing else"
            )
        image = args[1]
        if not _looks_like_local_file(image):
            raise PolicyViolation(
                f"fastboot boot {image!r}: not an existing local file "
                "(a partition name or a missing file is refused)"
            )
        if _PARTITION_LIKE.match(image) and not Path(image).exists():
            raise PolicyViolation(f"fastboot boot {image!r} looks like a partition name")
        return args

    if verb == "reboot":
        if len(args) == 1:
            return args
        if len(args) == 2 and args[1].lower() in {"bootloader", "fastboot"}:
            return args
        raise PolicyViolation(f"fastboot reboot target not allowed: {args[1:]}")

    if verb == "get_staged":
        if len(args) != 2:
            raise PolicyViolation("fastboot get_staged takes exactly one host file")
        target = Path(args[1])
        if target.is_dir():
            raise PolicyViolation(f"fastboot get_staged {args[1]!r} is a directory")
        return args

    if verb == "fetch":
        # Device -> host only, and only when a caller explicitly opts in.  It is
        # not used by this tool's boot path.
        if not allow_remote_fetch:
            raise PolicyViolation("fastboot fetch is disabled for the boot workflow")
        if len(args) != 3:
            raise PolicyViolation("fastboot fetch takes a partition and a host file")
        return args

    raise PolicyViolation(f"fastboot verb {verb!r} is not handled")


# --------------------------------------------------------------------------- #
# adb
# --------------------------------------------------------------------------- #

#: adb subcommands that only read or report.
ALLOWED_ADB_SUBCOMMANDS = frozenset(
    {
        "devices",
        "version",
        "get-state",
        "start-server",
        "kill-server",
        "shell",
        "exec-out",
        "pull",
        "reboot",
    }
)

#: First word of an ``adb shell`` command that only reads.
READ_ONLY_SHELL = frozenset(
    {
        "getprop",
        "cat",
        "ls",
        "ll",
        "uname",
        "dumpsys",
        "id",
        "wm",
        "settings",
        "pm",
        "logcat",
        "getevent",
        "getenforce",
        "which",
        "lsmod",
        "df",
        "free",
        "uptime",
        "date",
        "ps",
        "stat",
        "readlink",
        "head",
        "tail",
        "wc",
        "grep",
        "find",
        "test",
        "printf",
    }
)

#: Words that imply a write, a shell, or privilege escalation.  They are refused
#: even when the first word is read-only (e.g. ``cat x > y`` is caught by the
#: metacharacter rule; ``dumpsys ...; reboot`` by the same rule).
FORBIDDEN_SHELL_WORDS = frozenset(
    {
        "dd",
        "rm",
        "rmdir",
        "mv",
        "cp",
        "mkdir",
        "touch",
        "chmod",
        "chown",
        "ln",
        "truncate",
        "tee",
        "setprop",
        "su",
        "sh",
        "bash",
        "reboot",
        "sync",
        "format",
        "mkfs",
        "mkfs.ext4",
        "mkfs.f2fs",
        "fsck",
        "wipe",
        "install",
        "uninstall",
        "remount",
        "mount",
        "umount",
        "flash",
        "erase",
        "sideload",
        "push",
        "root",
        "unroot",
        "disable-verity",
        "enable-verity",
        "enable",
        "disable",
        "write",
        "restorecon",
        "setenforce",
        "run-as",
        "exec",
        "eval",
    }
)

#: Shell metacharacters.  Any of these means the command is not a simple read.
SHELL_METACHARACTERS = set(";|&<>$`\n\r\\")

#: Where ``adb pull`` may read from.  Reading is allowed; the host side is a local
#: write, which is permitted by the storage policy.
ALLOWED_PULL_ROOTS = (
    "/sys/firmware/fdt",
    "/sys/devices/soc0",
    "/sys/class",
    "/sys/bus",
    "/sys/kernel",
    "/proc",
    "/dev/block/by-name",
    "/vendor/firmware",
    "/vendor/lib/modules",
    "/system/lib/modules",
    "/odm/firmware",
)


def _check_shell(words: Sequence[str]) -> None:
    if not words:
        raise PolicyViolation("empty adb shell command")

    for word in words:
        if word in FORBIDDEN_SHELL_WORDS:
            raise PolicyViolation(f"adb shell word {word!r} is not read-only")

    head = words[0].lower()

    # ``busybox``/``toybox`` prefixes are unwrapped once.
    if head in {"busybox", "toybox"} and len(words) > 1:
        return _check_shell(words[1:])

    if head not in READ_ONLY_SHELL:
        raise PolicyViolation(f"adb shell command {words[0]!r} is not on the read-only allow-list")

    if head == "settings":
        if len(words) < 2 or words[1] != "get":
            raise PolicyViolation("only 'settings get' is allowed")
    elif head == "pm":
        if len(words) < 2 or words[1] not in {"list", "path", "dump"}:
            raise PolicyViolation("only 'pm list', 'pm path' and 'pm dump' are allowed")
    elif head == "wm":
        if len(words) > 2 or (len(words) == 2 and words[1] not in {"size", "density"}):
            raise PolicyViolation("only 'wm size' and 'wm density' are allowed")
    elif head == "logcat":
        if "-d" not in words:
            raise PolicyViolation("only 'logcat -d' (dump and exit) is allowed")
    elif head == "find":
        # find can execute; refuse -exec/-delete.
        for bad in ("-exec", "-execdir", "-delete", "-ok"):
            if bad in words:
                raise PolicyViolation(f"find {bad} is not read-only")


def _split_shell(command: str) -> list[str]:
    if not command.strip():
        raise PolicyViolation("empty adb shell command")
    for ch in command:
        if ch in SHELL_METACHARACTERS:
            raise PolicyViolation(
                f"adb shell metacharacter {ch!r} refused: only a single simple read command is allowed"
            )
    try:
        return shlex.split(command, posix=True)
    except ValueError as exc:  # unbalanced quotes
        raise PolicyViolation(f"adb shell command cannot be parsed: {exc}") from exc


def check_adb(argv: Sequence[str]) -> list[str]:
    """Validate an adb argument vector (without the ``adb`` executable)."""

    args = [str(a) for a in argv]
    if not args:
        raise PolicyViolation("empty adb command")

    # Strip the global options we use: -s SERIAL, -d, -e.
    while args and args[0].startswith("-"):
        if args[0] in {"-s", "-t"}:
            if len(args) < 3:
                raise PolicyViolation(f"adb {args[0]} needs a value")
            args = args[2:]
        elif args[0] in {"-d", "-e"}:
            args = args[1:]
        else:
            raise PolicyViolation(f"adb global option not allowed: {args[0]}")

    if not args:
        raise PolicyViolation("empty adb command after global options")

    sub = args[0].lower()
    if sub not in ALLOWED_ADB_SUBCOMMANDS:
        raise PolicyViolation(
            f"adb subcommand {sub!r} is not on the allow-list "
            f"({', '.join(sorted(ALLOWED_ADB_SUBCOMMANDS))})"
        )

    if sub in {"devices", "version", "get-state", "start-server", "kill-server"}:
        return args

    if sub in {"shell", "exec-out"}:
        if len(args) < 2:
            raise PolicyViolation(f"adb {sub} needs a command")
        # ``adb shell echo foo`` arrives as several words; join them back so the
        # metacharacter check sees the whole command, then validate the words.
        command = " ".join(args[1:])
        words = _split_shell(command)
        _check_shell(words)
        return args

    if sub == "pull":
        if len(args) != 3:
            raise PolicyViolation("adb pull takes a remote path and a local path")
        remote = args[1]
        if not remote.startswith("/"):
            raise PolicyViolation("adb pull remote path must be absolute")
        if not any(remote == root or remote.startswith(root + "/") for root in ALLOWED_PULL_ROOTS):
            raise PolicyViolation(f"adb pull {remote!r} is outside the read-only roots")
        return args

    if sub == "reboot":
        if len(args) == 1:
            return args
        if len(args) == 2 and args[1].lower() in {"bootloader", "recovery", "fastboot", "sideload"}:
            return args
        raise PolicyViolation(f"adb reboot target not allowed: {args[1:]}")

    raise PolicyViolation(f"adb subcommand {sub!r} is not handled")


def describe_policy() -> str:
    """A short, human-readable summary for ``verify-safety`` output."""

    return (
        "Allowed device operations:\n"
        "  fastboot: devices, getvar <read-only>, boot <local file>, reboot, "
        "get_staged <host file>\n"
        "  adb: devices, version, get-state, shell <read-only>, exec-out <read-only>, "
        "pull <under read-only roots>, reboot\n"
        "Refused, always: flash, erase, format, set_active, partition, resize, "
        "oem/flashing lock or unlock, -w, adb push/root/remount/sideload/install"
    )
