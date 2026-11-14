"""The published wheel carries every tracked file of the package.

CD runs ``uv build``, which builds the sdist first and then the wheel from
that sdist. A package file that the sdist ``include`` list misses is
therefore silently dropped from the wheel, even when the wheel target lists
it, and works only from a source checkout. ``data/tier1_libraries.json`` was
lost that way: an installed wet seeded no Tier 1 library, so ``docs_reindex``
answered "not found in index" for every curated name.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracked_package_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "src/wet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        line.removeprefix("src/")
        for line in result.stdout.splitlines()
        if line and "__pycache__" not in line
    }


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_wheel_built_like_cd_ships_every_package_file(tmp_path: Path):
    subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    (wheel,) = tmp_path.glob("*.whl")
    shipped = set(zipfile.ZipFile(wheel).namelist())

    missing = sorted(_tracked_package_files() - shipped)

    assert not missing, "dropped from the wheel:\n" + "\n".join(missing)
