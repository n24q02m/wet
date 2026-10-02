"""Supply-chain guard: security-pinned dependencies must stay patched.

Several dependencies carry explicit CVE-driven floors in ``pyproject.toml``
(see the inline comments there). A lock regeneration that silently dropped
or weakened a pin would reintroduce the vulnerability, so the resolved
``uv.lock`` versions are asserted here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

_LOCK = Path(__file__).resolve().parent.parent / "uv.lock"

# package name -> minimum patched version (the CVE is closed at/above this).
_SECURITY_FLOORS = {
    "urllib3": "2.7.0",  # GHSA-qccp-gfcp-xxvc, GHSA-mf9v-mfxr-j63j (2 high)
    "langsmith": "0.8.0",  # GHSA-3644-q5cj-c5c7 (high)
    "fastmcp": "3.2.4",  # keep off CVE-vulnerable 2.x line
}


def _locked_versions() -> dict[str, str]:
    data = tomllib.loads(_LOCK.read_text(encoding="utf-8"))
    return {pkg["name"]: pkg["version"] for pkg in data["package"]}


def test_uv_lock_exists():
    assert _LOCK.is_file(), f"uv.lock not found at {_LOCK}"


@pytest.mark.parametrize(("name", "floor"), sorted(_SECURITY_FLOORS.items()))
def test_security_pinned_dependency_meets_floor(name: str, floor: str):
    locked = _locked_versions()
    assert name in locked, f"{name} missing from uv.lock"
    assert Version(locked[name]) >= Version(floor), (
        f"{name} {locked[name]} is below the security floor {floor}"
    )
