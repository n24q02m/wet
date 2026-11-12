"""Auto-setup utilities for WET MCP Server.

This module handles automatic first-run setup:
- Install SearXNG from GitHub (metasearch engine)
- Install the Playwright AND Patchright Chromium builds + system deps
- Create configuration directories

Setup runs automatically on first server start.
"""

import platform
import subprocess
import sys
from pathlib import Path

from loguru import logger

# Marker file to track if setup has been run (legacy dir name was ~/.wet)
SETUP_MARKER = Path.home() / ".wet" / ".setup-complete"

# SearXNG install URL (zip avoids git clone filename issues)
_SEARXNG_INSTALL_URL = (
    "https://github.com/searxng/searxng/archive/refs/heads/master.zip"
)


def _find_searx_package_dir() -> Path | None:
    """Find SearXNG package directory via importlib."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("searx")
        if spec and spec.submodule_search_locations:
            return Path(spec.submodule_search_locations[0])
    except Exception:
        pass
    return None


def patch_searxng_version() -> None:
    """Create searx.version_frozen module if missing.

    SearXNG build system uses `git describe` to generate version_frozen.py.
    When installing from a zip archive (no .git directory), this module is
    not created, causing ImportError at runtime.
    """
    try:
        searx_dir = _find_searx_package_dir()
        if not searx_dir:
            return

        vf = searx_dir / "version_frozen.py"
        if not vf.exists():
            vf.write_text(
                'VERSION_STRING = "0.0.0"\n'
                'VERSION_TAG = "v0.0.0"\n'
                'DOCKER_TAG = ""\n'
                'GIT_URL = "https://github.com/searxng/searxng"\n'
                'GIT_BRANCH = "master"\n'
            )
            logger.debug(f"Created SearXNG version_frozen: {vf}")
    except Exception as e:
        logger.warning(f"Failed to patch SearXNG version: {e}")


def patch_searxng_windows() -> None:
    """Patch SearXNG valkeydb.py for Windows compatibility.

    SearXNG's valkeydb.py imports ``pwd`` (Unix-only) at module level,
    but only uses it to log the username on Valkey connection errors.
    This patches it to gracefully handle the missing module on Windows.
    """
    if platform.system() != "Windows":
        return

    try:
        searx_dir = _find_searx_package_dir()
        if not searx_dir:
            return

        valkeydb_path = searx_dir / "valkeydb.py"
        if not valkeydb_path.exists():
            return

        content = valkeydb_path.read_text(encoding="utf-8")

        # Skip if already patched
        if "except ImportError" in content and "pwd = None" in content:
            return

        if "import pwd" not in content:
            return

        # Patch: wrap `import pwd` in try/except
        content = content.replace(
            "import pwd\n",
            "try:\n    import pwd\nexcept ImportError:\n    pwd = None\n",
        )

        # Patch: guard pwd.getpwuid usage in error handler
        content = content.replace(
            "        _pw = pwd.getpwuid(os.getuid())\n"
            '        logger.exception("[%s (%s)] can\'t connect valkey DB ...", '
            "_pw.pw_name, _pw.pw_uid)",
            "        if pwd and hasattr(os, 'getuid'):\n"
            "            _pw = pwd.getpwuid(os.getuid())\n"
            "            logger.exception(\"[%s (%s)] can't connect valkey DB "
            '...", _pw.pw_name, _pw.pw_uid)\n'
            "        else:\n"
            '            logger.exception("can\'t connect valkey DB ...")',
        )

        valkeydb_path.write_text(content, encoding="utf-8")
        logger.debug(f"Patched SearXNG valkeydb.py for Windows: {valkeydb_path}")
    except Exception as e:
        logger.warning(f"Failed to patch SearXNG for Windows: {e}")


def needs_setup() -> bool:
    """Check if setup needs to run."""
    return not SETUP_MARKER.exists()


def _get_pip_command() -> list[str]:
    """Get cross-platform pip install command."""
    import shutil

    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "pip", "install", "--python", sys.executable]

    pip_path = shutil.which("pip")
    if pip_path:
        return [pip_path, "install"]

    return [sys.executable, "-m", "pip", "install"]


def _install_searxng() -> bool:
    """Install SearXNG Python package from GitHub zip archive.

    Pre-installs build dependencies, then installs SearXNG with
    --no-build-isolation for reliable builds across platforms.

    Returns:
        True if installation succeeded or already installed.
    """
    if _find_searx_package_dir():
        logger.debug("SearXNG already installed")
        return True

    logger.info("Installing SearXNG from GitHub...")
    try:
        # Pre-install build dependencies
        pip_cmd = _get_pip_command()
        deps_result = subprocess.run(
            [
                *pip_cmd,
                "--quiet",
                "msgspec",
                "setuptools",
                "wheel",
                "pyyaml",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=120,
        )
        if deps_result.returncode != 0:
            logger.error(f"Build deps install failed: {deps_result.stderr[:300]}")
            return False

        # Install SearXNG with --no-build-isolation
        result = subprocess.run(
            [
                *pip_cmd,
                "--quiet",
                "--no-build-isolation",
                _SEARXNG_INSTALL_URL,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("SearXNG installed successfully")
            patch_searxng_version()
            patch_searxng_windows()
            return True
        else:
            logger.error(f"SearXNG install failed: {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("SearXNG installation timed out")
        return False
    except Exception as e:
        logger.error(f"SearXNG install error: {e}")
        return False


# One Chromium consumer per entry. wet drives TWO Playwright forks with
# different pinned browser builds: crawl4ai uses ``playwright`` (build 1254
# with playwright 1.65) and ``extract interact`` uses ``patchright`` (build
# 1248 with patchright 1.64). ``ms-playwright`` keeps one directory per build,
# so installing only playwright's left every interact call failing with
# "Executable doesn't exist ... chrome-headless-shell-1248".
_BROWSER_INSTALLERS = ("playwright", "patchright")


def _install_browser(module: str) -> bool:
    """Install Chromium (plus system deps) for one Playwright-compatible module.

    ``--with-deps`` needs a system package manager, so it is retried without on
    platforms where it is unsupported instead of failing the whole setup.
    """
    base = [sys.executable, "-m", module, "install", "chromium"]
    for extra in (["--with-deps"], []):
        try:
            result = subprocess.run(
                [*base, *extra],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"{module}: chromium install timed out (900 s)")
            continue
        if result.returncode == 0:
            logger.info(f"{module}: chromium installed")
            return True
        logger.warning(
            f"{module}: chromium install with {' '.join(extra) or 'no flags'} "
            f"failed (exit {result.returncode}): "
            f"{(result.stderr or '').strip()[:300]}"
        )
    return False


def _setup_crawl4ai() -> bool:
    """Run the crawl4ai post-install steps wet depends on.

    - ``.crawl4ai`` home directory + database migration (``crawl4ai.install``)
    - Chromium for ``playwright`` (crawl4ai's renderer)
    - Chromium for ``patchright`` (``extract interact`` / stealth sessions)

    This ensures all required system libraries are installed on every OS
    (Windows, Ubuntu 20+, macOS, etc.) without requiring manual steps.

    Returns:
        True if setup succeeded.
    """
    logger.info("Running crawl4ai setup (browsers + system deps)...")
    try:
        # 1. Setup home directory and run migration safely in a subprocess
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from crawl4ai.install import setup_home_directory, run_migration; setup_home_directory(); run_migration()",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2. Install the Chromium build each browser consumer pins
        installed = [(m, _install_browser(m)) for m in _BROWSER_INSTALLERS]
        missing = [m for m, ok in installed if not ok]
        if missing:
            logger.error(f"browser install failed for: {', '.join(missing)}")
            return False

        logger.info("crawl4ai setup completed successfully")
        return True
    except Exception as e:
        logger.error(f"crawl4ai setup failed: {e}")
        logger.warning(
            "crawl/extract features may not work. "
            "Try running 'crawl4ai-setup' manually."
        )
        return False


def run_auto_setup() -> bool:
    """Run automatic setup on first start.

    Installs all required components:
    1. SearXNG (metasearch engine, from GitHub)
    2. Playwright + Patchright chromium + system deps (crawl4ai, interact)

    Returns:
        True if setup succeeded or was already done, False on failure.
    """
    if not needs_setup():
        logger.debug("Setup already complete, skipping")
        return True

    logger.info("First run detected, running auto-setup...")

    success = True

    # Step 1: Create config directory (legacy dir name was ~/.wet)
    config_dir = Path.home() / ".wet"
    config_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Created config directory: {config_dir}")

    # Step 2: Install SearXNG from GitHub
    if not _install_searxng():
        logger.warning("SearXNG not installed, search will use external URL")
        # Don't fail setup entirely - extract/crawl still works

    # Step 3: Run crawl4ai setup (Playwright + system deps + patchright)
    if not _setup_crawl4ai():
        success = False

    # Mark setup as complete
    if success:
        SETUP_MARKER.touch()
        logger.info("Auto-setup complete!")

    return success
