"""URL change monitoring and semantic diff noise filtering (WET-48, WET-49)."""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import Any

# Common high-churn boilerplate lines excluded from semantic change comparison.
_TIMESTAMP_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)\b"
)
_RELATIVE_TIME_RE = re.compile(
    r"\b(?:updated|last updated|modified|published|generated)\s+\d+\s+(?:second|minute|hour|day)s?\s+ago\b",
    re.IGNORECASE,
)
_NONCE_TOKEN_RE = re.compile(
    r"\b(?:nonce|csrf[_-]?token|request[_-]?id|trace[_-]?id|build[_-]?id)[=:\s\"']+[A-Za-z0-9_-]{6,}\b",
    re.IGNORECASE,
)
_COPYRIGHT_YEAR_RE = re.compile(
    r"(?:©|copyright)\s*\d{4}(?:\s*[-–]\s*\d{4})?", re.IGNORECASE
)
_BOILERPLATE_LINE_RE = re.compile(
    r"^\s*(?:skip to (?:main )?content|cookie (?:policy|preferences|settings)|"
    r"all rights reserved|back to top|advertisement|sponsored)\s*$",
    re.IGNORECASE,
)


def normalize_for_diff(content: str) -> tuple[str, int]:
    """Normalize ephemeral timestamps, nonces, and boilerplate lines out of content.

    Returns ``(normalized_text, filtered_line_count)`` so callers can tell when
    a raw diff consisted exclusively of noise (e.g., clock ticks or ads).
    """
    if not content:
        return "", 0
    cleaned_lines: list[str] = []
    noise_lines = 0
    for raw_line in content.splitlines():
        line = _TIMESTAMP_RE.sub("<TIMESTAMP>", raw_line)
        line = _RELATIVE_TIME_RE.sub("<RELATIVE_TIME>", line)
        line = _NONCE_TOKEN_RE.sub("<TOKEN>", line)
        line = _COPYRIGHT_YEAR_RE.sub("<COPYRIGHT>", line)
        if _BOILERPLATE_LINE_RE.match(line):
            noise_lines += 1
            continue
        if line != raw_line:
            noise_lines += 1
        cleaned_lines.append(line.rstrip())
    return "\n".join(cleaned_lines).strip(), noise_lines


def classify_change(
    old_content: str,
    new_content: str,
    *,
    url: str = "",
    max_diff_chars: int = 20_000,
) -> dict[str, Any]:
    """Compare two content snapshots with deterministic noise filtering.

    Returns a summary with ``change_status`` (``same`` | ``noise_only`` |
    ``meaningful``), ``change_ratio`` (0.0–1.0), ``noise_lines_filtered``,
    and unified ``diff``.
    """
    if old_content == new_content:
        return {
            "change_status": "same",
            "meaningful": False,
            "change_ratio": 0.0,
            "noise_lines_filtered": 0,
            "diff": "",
        }

    norm_old, noise_old = normalize_for_diff(old_content)
    norm_new, noise_new = normalize_for_diff(new_content)
    filtered = noise_old + noise_new

    if norm_old == norm_new:
        return {
            "change_status": "noise_only",
            "meaningful": False,
            "change_ratio": 0.0,
            "noise_lines_filtered": filtered,
            "diff": "",
        }

    old_lines = norm_old.splitlines()
    new_lines = norm_new.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    change_ratio = round(1.0 - matcher.ratio(), 4)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{url or 'snapshot'} (old)",
        tofile=f"{url or 'snapshot'} (new)",
        lineterm="",
        n=3,
    )
    diff_text = "\n".join(diff_lines)
    if len(diff_text) > max_diff_chars:
        diff_text = diff_text[:max_diff_chars] + "\n... (diff truncated at 20000 chars)"

    return {
        "change_status": "meaningful",
        "meaningful": True,
        "change_ratio": change_ratio,
        "noise_lines_filtered": filtered,
        "diff": diff_text,
    }


def content_digest(text: str) -> str:
    """Return a short deterministic SHA-256 digest for normalized snapshot content."""
    norm, _ = normalize_for_diff(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
