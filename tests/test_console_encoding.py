"""Windows console Unicode encoding guard in wet_mcp.server.

Bug: on Windows the default console encoding is cp1252, so emitting
Vietnamese / non-ASCII text on stdout/stderr raises UnicodeEncodeError and
crashes the server. Fix: at import time, on win32, reconfigure stdin/stdout/
stderr to utf-8 (errors="replace").

This test exercises the exact module-level guard against real TextIOWrapper
streams under both a simulated win32 and a non-win32 platform, so it runs
identically on every OS and fails if the guard is removed.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path


def _extract_win32_guard() -> str:
    """Return the source of the module-level ``if sys.platform == "win32"``
    guard from wet_mcp/server.py.

    Fails loudly if the guard is missing (mutation sanity: deleting the fix
    makes this raise, so every test below fails too).
    """
    src = (
        Path(__file__).resolve().parent.parent / "src" / "wet_mcp" / "server.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.If):
            cond = node.test
            if (
                isinstance(cond, ast.Compare)
                and isinstance(cond.left, ast.Attribute)
                and cond.left.attr == "platform"
                and isinstance(cond.comparators[0], ast.Constant)
                and cond.comparators[0].value == "win32"
            ):
                return ast.get_source_segment(src, node) or ""
    raise AssertionError("win32 console-encoding guard missing from wet_mcp/server.py")


def _make_stream() -> io.TextIOWrapper:
    """A real TextIOWrapper pinned to a non-utf-8 (cp1252) encoding."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def _run_guard(platform: str) -> dict[str, io.TextIOWrapper]:
    """Execute the real guard with real cp1252 streams under a sim platform."""
    guard = _extract_win32_guard()
    streams = {
        "stdin": _make_stream(),
        "stdout": _make_stream(),
        "stderr": _make_stream(),
    }

    class _FakeSys:
        pass

    fake_sys = _FakeSys()
    fake_sys.platform = platform
    fake_sys.stdin = streams["stdin"]
    fake_sys.stdout = streams["stdout"]
    fake_sys.stderr = streams["stderr"]
    exec(guard, {"sys": fake_sys, "io": io})  # noqa: S102 - trusted project source
    return streams


def test_win32_reconfigures_all_three_streams_to_utf8() -> None:
    streams = _run_guard("win32")
    for name, stream in streams.items():
        assert stream.encoding == "utf-8", name
        assert stream.errors == "replace", name


def test_non_win32_leaves_stream_encoding_untouched() -> None:
    streams = _run_guard("linux")
    for name, stream in streams.items():
        assert stream.encoding == "cp1252", name
