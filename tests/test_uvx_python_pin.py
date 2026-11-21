"""Documented uvx launches of n24q02m-wet pin the one supported Python.

n24q02m-wet declares ``Requires-Python ==3.13.*``. Without ``--python 3.13``
uvx uses the default interpreter: below 3.13 the install fails, and on 3.14 or
newer uv ignores the upper bound and runs wet on a Python it does not support.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# CHANGELOG and ADRs record history, legacy/ holds the frozen wet-mcp stub as
# published, and tests describe gates rather than give install steps.
SKIPPED = ("CHANGELOG.md:", "docs/adr/", "legacy/", "tests/")


def test_documented_uvx_launches_pin_python_3_13():
    result = subprocess.run(
        ["git", "grep", "-nE", "-e", r"uvx (--from )?n24q02m-wet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    hits = [
        line
        for line in result.stdout.splitlines()
        if line and not line.startswith(SKIPPED)
    ]
    assert not hits, "uvx launch without --python 3.13:\n" + "\n".join(hits)
