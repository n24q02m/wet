import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from wet_mcp.setup import (
    _find_searx_package_dir,
    _get_pip_command,
    _install_searxng,
    _setup_crawl4ai,
    needs_setup,
    patch_searxng_version,
    patch_searxng_windows,
    run_auto_setup,
)

# Test _find_searx_package_dir


@patch("importlib.util.find_spec")
def test_find_searx_package_dir_found(mock_find_spec):
    mock_spec = MagicMock()
    mock_spec.submodule_search_locations = ["/path/to/searx"]
    mock_find_spec.return_value = mock_spec

    result = _find_searx_package_dir()
    assert result == Path("/path/to/searx")


@patch("importlib.util.find_spec")
def test_find_searx_package_dir_not_found(mock_find_spec):
    mock_spec = MagicMock()
    mock_spec.submodule_search_locations = []
    mock_find_spec.return_value = mock_spec

    assert _find_searx_package_dir() is None


@patch("importlib.util.find_spec", side_effect=Exception("Test error"))
def test_find_searx_package_dir_exception(mock_find_spec):
    assert _find_searx_package_dir() is None


# Test patch_searxng_version


@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_version_success(mock_find_dir):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = False

    patch_searxng_version()

    mock_file.write_text.assert_called_once()
    args = mock_file.write_text.call_args[0][0]
    assert "VERSION_STRING =" in args


@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_version_already_exists(mock_find_dir):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = True

    patch_searxng_version()

    mock_file.write_text.assert_not_called()


@patch("wet_mcp.setup.Path")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_version_no_dir(mock_find_dir, mock_path):
    mock_find_dir.return_value = None
    patch_searxng_version()
    # Should exit early without any Path operations
    mock_path.assert_not_called()


@patch("wet_mcp.setup._find_searx_package_dir", side_effect=Exception("Test error"))
def test_patch_searxng_version_exception(mock_find_dir):
    patch_searxng_version()
    # Exception should be caught and logged


# Test patch_searxng_windows


@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_success(mock_find_dir, mock_system):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = True

    original_content = (
        "import pwd\n"
        "def foo():\n"
        "        _pw = pwd.getpwuid(os.getuid())\n"
        '        logger.exception("[%s (%s)] can\'t connect valkey DB ...", _pw.pw_name, _pw.pw_uid)\n'
    )
    mock_file.read_text.return_value = original_content

    patch_searxng_windows()

    mock_file.write_text.assert_called_once()
    written_content = mock_file.write_text.call_args[0][0]
    assert (
        "try:\n    import pwd\nexcept ImportError:\n    pwd = None\n" in written_content
    )
    assert "if pwd and hasattr(os, 'getuid'):" in written_content


@patch("platform.system", return_value="Linux")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_not_win32(mock_find_dir, mock_system):
    patch_searxng_windows()
    mock_find_dir.assert_not_called()


@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_already_patched(mock_find_dir, mock_system):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = True

    original_content = "try:\n    import pwd\nexcept ImportError:\n    pwd = None\n"
    mock_file.read_text.return_value = original_content

    patch_searxng_windows()
    mock_file.write_text.assert_not_called()


@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_no_pwd_import(mock_find_dir, mock_system):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = True

    mock_file.read_text.return_value = "def foo(): pass\n"

    patch_searxng_windows()
    mock_file.write_text.assert_not_called()


@patch("wet_mcp.setup.Path")
@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_no_dir(mock_find_dir, mock_system, mock_path):
    mock_find_dir.return_value = None
    patch_searxng_windows()
    # Should exit early without any Path operations
    mock_path.assert_not_called()


@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_no_valkeydb(mock_find_dir, mock_system):
    mock_dir = MagicMock(spec=Path)
    mock_find_dir.return_value = mock_dir
    mock_file = MagicMock(spec=Path)
    mock_dir.__truediv__.return_value = mock_file
    mock_file.exists.return_value = False

    patch_searxng_windows()
    mock_file.read_text.assert_not_called()


@patch("platform.system", return_value="Windows")
@patch("wet_mcp.setup._find_searx_package_dir", side_effect=Exception("Test error"))
def test_patch_searxng_windows_exception(mock_find_dir, mock_system):
    patch_searxng_windows()


# Test needs_setup


@patch("wet_mcp.setup.SETUP_MARKER")
def test_needs_setup_true(mock_marker):
    mock_marker.exists.return_value = False
    assert needs_setup() is True


@patch("wet_mcp.setup.SETUP_MARKER")
def test_needs_setup_false(mock_marker):
    mock_marker.exists.return_value = True
    assert needs_setup() is False


# Test _get_pip_command


@patch("shutil.which")
@patch("sys.executable", "/usr/bin/python3")
def test_get_pip_command_uv(mock_which):
    def which_side_effect(name):
        if name == "uv":
            return "/path/to/uv"
        return None

    mock_which.side_effect = which_side_effect

    cmd = _get_pip_command()
    assert cmd == ["/path/to/uv", "pip", "install", "--python", "/usr/bin/python3"]


@patch("shutil.which")
@patch("sys.executable", "/usr/bin/python3")
def test_get_pip_command_pip(mock_which):
    def which_side_effect(name):
        if name == "pip":
            return "/path/to/pip"
        return None

    mock_which.side_effect = which_side_effect

    cmd = _get_pip_command()
    assert cmd == ["/path/to/pip", "install"]


@patch("shutil.which", return_value=None)
@patch("sys.executable", "/usr/bin/python3")
def test_get_pip_command_sys_executable(mock_which):
    cmd = _get_pip_command()
    assert cmd == ["/usr/bin/python3", "-m", "pip", "install"]


# Test _install_searxng


@patch("wet_mcp.setup._find_searx_package_dir", return_value=Path("/mock/searx"))
def test_install_searxng_already_installed(_mock_find):
    # If _find_searx_package_dir returns a path, should return True immediately
    assert _install_searxng() is True


@patch("wet_mcp.setup._find_searx_package_dir", return_value=None)
@patch("wet_mcp.setup._get_pip_command", return_value=["pip", "install"])
@patch("subprocess.run")
@patch("wet_mcp.setup.patch_searxng_version")
@patch("wet_mcp.setup.patch_searxng_windows")
def test_install_searxng_success(
    mock_patch_win, mock_patch_ver, mock_run, mock_get_pip, _mock_find
):
    # Simulate both subprocesses returning 0
    mock_run.return_value = MagicMock(returncode=0)

    assert _install_searxng() is True
    assert mock_run.call_count == 2
    mock_patch_ver.assert_called_once()
    mock_patch_win.assert_called_once()


@patch("wet_mcp.setup._find_searx_package_dir", return_value=None)
@patch("wet_mcp.setup._get_pip_command", return_value=["pip", "install"])
@patch("subprocess.run")
def test_install_searxng_deps_fail(mock_run, mock_get_pip, _mock_find):
    mock_run.return_value = MagicMock(returncode=1, stderr="deps failed")

    assert _install_searxng() is False
    assert mock_run.call_count == 1


@patch("wet_mcp.setup._find_searx_package_dir", return_value=None)
@patch("wet_mcp.setup._get_pip_command", return_value=["pip", "install"])
@patch("subprocess.run")
def test_install_searxng_main_fail(mock_run, mock_get_pip, _mock_find):
    # First call (deps) succeeds, second call (main) fails
    mock_run.side_effect = [
        MagicMock(returncode=0),
        MagicMock(returncode=1, stderr="main failed"),
    ]

    assert _install_searxng() is False
    assert mock_run.call_count == 2


@patch("wet_mcp.setup._find_searx_package_dir", return_value=None)
@patch("wet_mcp.setup._get_pip_command", return_value=["pip", "install"])
@patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=120))
def test_install_searxng_timeout(mock_run, mock_get_pip, _mock_find):
    assert _install_searxng() is False


@patch("wet_mcp.setup._find_searx_package_dir", return_value=None)
@patch("wet_mcp.setup._get_pip_command", side_effect=Exception("Test error"))
def test_install_searxng_exception(mock_get_pip, _mock_find):
    assert _install_searxng() is False


# Test _setup_crawl4ai


@patch("subprocess.run")
def test_setup_crawl4ai_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert _setup_crawl4ai() is True
    assert mock_run.call_count == 2


@patch("subprocess.run", side_effect=Exception("Test error"))
def test_setup_crawl4ai_exception(mock_run):
    assert _setup_crawl4ai() is False


# Test run_auto_setup


@patch("wet_mcp.setup.needs_setup", return_value=False)
def test_run_auto_setup_not_needed(mock_needs_setup):
    assert run_auto_setup() is True


@patch("wet_mcp.setup.needs_setup", return_value=True)
@patch("wet_mcp.setup._install_searxng", return_value=True)
@patch("wet_mcp.setup._setup_crawl4ai", return_value=True)
@patch("wet_mcp.setup.SETUP_MARKER")
@patch("pathlib.Path.mkdir")
def test_run_auto_setup_success(
    mock_mkdir, mock_marker, mock_setup_crawl4ai, mock_install_searxng, mock_needs_setup
):
    assert run_auto_setup() is True
    mock_mkdir.assert_called_once()
    mock_install_searxng.assert_called_once()
    mock_setup_crawl4ai.assert_called_once()
    mock_marker.touch.assert_called_once()


@patch("wet_mcp.setup.needs_setup", return_value=True)
@patch("wet_mcp.setup._install_searxng", return_value=False)
@patch("wet_mcp.setup._setup_crawl4ai", return_value=True)
@patch("wet_mcp.setup.SETUP_MARKER")
@patch("pathlib.Path.mkdir")
def test_run_auto_setup_searxng_fail(
    mock_mkdir, mock_marker, mock_setup_crawl4ai, mock_install_searxng, mock_needs_setup
):
    assert run_auto_setup() is True
    mock_marker.touch.assert_called_once()


@patch("wet_mcp.setup.needs_setup", return_value=True)
@patch("wet_mcp.setup._install_searxng", return_value=True)
@patch("wet_mcp.setup._setup_crawl4ai", return_value=False)
@patch("wet_mcp.setup.SETUP_MARKER")
@patch("pathlib.Path.mkdir")
def test_run_auto_setup_crawl4ai_fail(
    mock_mkdir, mock_marker, mock_setup_crawl4ai, mock_install_searxng, mock_needs_setup
):
    assert run_auto_setup() is False
    mock_marker.touch.assert_not_called()
