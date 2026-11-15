"""
Exception hierarchy for kbuild.
"""

from __future__ import annotations


class KbuildError(Exception):
    """Base exception for all kbuild errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code

    def __str__(self) -> str:
        return self.message


class PreflightError(KbuildError):
    """Raised when environment or tool requirements are not met."""

    def __init__(self, message: str, exit_code: int = 3):
        super().__init__(message, exit_code=exit_code)


class ToolchainError(KbuildError):
    """Raised when Clang toolchain cannot be downloaded, verified, or executed."""

    def __init__(self, message: str, exit_code: int = 4):
        super().__init__(message, exit_code=exit_code)


class BuildError(KbuildError):
    """Raised when kernel configuration or compilation fails."""

    def __init__(self, message: str, exit_code: int = 5):
        super().__init__(message, exit_code=exit_code)


class IntegrationError(KbuildError):
    """Raised when KernelSU or NoMount setup or cleanup fails."""

    def __init__(self, message: str, exit_code: int = 6):
        super().__init__(message, exit_code=exit_code)


class PackagingError(KbuildError):
    """Raised when AnyKernel3 packaging or DTBO generation fails."""

    def __init__(self, message: str, exit_code: int = 7):
        super().__init__(message, exit_code=exit_code)


class UploadError(KbuildError):
    """Raised when Telegram or GoFile upload fails."""

    def __init__(self, message: str, exit_code: int = 8):
        super().__init__(message, exit_code=exit_code)


class InstallerError(KbuildError):
    """Raised during install, uninstall, or update operations."""

    def __init__(self, message: str, exit_code: int = 9):
        super().__init__(message, exit_code=exit_code)
