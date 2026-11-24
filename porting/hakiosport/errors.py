"""Typed failures with stable process exit codes.

The exit codes are part of the tool's contract: scripts and CI can tell a policy
refusal (nothing was done) from a boot failure (something was attempted).
"""

from __future__ import annotations


class HakiosError(Exception):
    """Base class. ``exit_code`` is what ``hakios_port.py`` returns."""

    exit_code = 1

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class UsageError(HakiosError):
    """Bad arguments, missing tool, or nothing to operate on."""

    exit_code = 2


class PolicyViolation(HakiosError):
    """A device command was refused before it ran. Nothing was sent to the device."""

    exit_code = 4


class UnsupportedHardware(HakiosError):
    """The device cannot perform the requested operation (e.g. no fastboot protocol).

    This is not a bug and must never be worked around by flashing.
    """

    exit_code = 3


class BuildBlocked(HakiosError):
    """A build cannot run here: wrong host, missing toolchain, or missing sources."""

    exit_code = 5


class BootFailed(HakiosError):
    """A boot was attempted and did not succeed."""

    exit_code = 6


class SafetyAuditFailed(HakiosError):
    """The storage-write audit found an unmitigated persistent write path."""

    exit_code = 7
