"""Structured error catalog for wet (E1xx config/runtime, E2xx operational)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """Canonical error codes surfaced across CLI diagnostics and tool responses."""

    # E1xx: Configuration, runtime, auth, transport
    E101_CONFIG_INVALID = "E101"
    E102_AUTH_MISCONFIGURED = "E102"
    E103_DB_NOT_READY = "E103"
    E104_UVX_SEARXNG_BLOCKED = "E104"
    E105_SERP_SCRAPE_DISABLED = "E105"
    E106_PROVIDER_KEY_MISSING = "E106"
    E107_PROFILE_INVALID = "E107"
    E108_CACHE_DISABLED = "E108"

    # E2xx: Execution, security, search, extraction, docs, jobs, monitors
    E201_SSRF_BLOCKED = "E201"
    E202_PROMPT_INJECTION_DETECTED = "E202"
    E203_SEARCH_EXHAUSTED = "E203"
    E204_PROVIDER_CIRCUIT_OPEN = "E204"
    E205_EXTRACT_FAILED = "E205"
    E206_DOCS_NOT_FOUND = "E206"
    E207_JOB_NOT_FOUND = "E207"
    E208_WATCH_NOT_FOUND = "E208"
    E209_VALIDATION_ERROR = "E209"
    E210_TIMEOUT = "E210"


@dataclass(frozen=True, slots=True)
class WetErrorDetail:
    """Structured error payload convertible to dict or human-readable text."""

    code: ErrorCode
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable error dict preserving the ``error`` key."""
        payload = {
            "error_code": self.code.value,
            "error": f"[{self.code.value}] {self.message}",
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload

    def format_text(self) -> str:
        """Render a single formatted error string."""
        if self.hint:
            return f"Error [{self.code.value}]: {self.message} Hint: {self.hint}"
        return f"Error [{self.code.value}]: {self.message}"


class WetError(RuntimeError):
    """Exception carrying a canonical :class:`ErrorCode`."""

    def __init__(self, code: ErrorCode, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.detail = WetErrorDetail(code=code, message=message, hint=hint)


def format_error(code: ErrorCode, message: str, *, hint: str = "") -> dict[str, str]:
    """Build a structured error envelope dictionary."""
    return WetErrorDetail(code=code, message=message, hint=hint).to_dict()
