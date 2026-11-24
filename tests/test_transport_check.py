"""Tests for ``wet.transport_check`` and the search-tool uvx gate.

Per spec ``2026-05-01-stdio-pure-http-multiuser.md`` §4.1.1: stdio uvx
mode must reject ``web.search`` / ``research`` / ``docs`` / ``similar``
because the bundled web-core SearXNG runner cannot install or start
SearXNG inside a pip-less uvx tool venv. Other actions (``extract`` /
``crawl`` / ``map`` / ``media``) hit upstream HTTP directly and remain
available.

Per spec ``2026-07-13-e0-1-uvx-guard-conditional-fix.md``, the gate is
conditional on ``search_backends.has_uvx_runnable_backend()``: it only
rejects when NO configured backend can run under uvx (no cloud key, no
external SearXNG). A cloud key (tavily/brave/exa) or an external
``SEARXNG_URL`` lets the four actions through.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, patch

import pytest
from structured import payload, text

import wet.transport_check as tc


@pytest.fixture
def _allow_real_uvx_detection(monkeypatch):
    """Undo the global ``_disable_uvx_tool_venv_detection`` fixture.

    Re-binds ``is_uvx_tool_venv`` in both the transport_check module and
    the server module to point at the real implementation again, so a
    test can monkeypatch the underlying signals (``sys.executable``,
    ``importlib.util.find_spec``) and observe the genuine outcome.
    """
    import wet.server as srv

    # Resolve the real function via the module ``__dict__`` source rather
    # than the live attribute, so we don't accidentally restore a stub
    # already installed by the autouse fixture.
    real_fn = tc._detect_uvx_tool_venv

    def real_is_uvx_tool_venv() -> bool:
        return real_fn()

    monkeypatch.setattr(tc, "is_uvx_tool_venv", real_is_uvx_tool_venv)
    monkeypatch.setattr(srv, "is_uvx_tool_venv", real_is_uvx_tool_venv)
    tc.reset_cache()
    yield
    tc.reset_cache()


# ---------------------------------------------------------------------------
# is_uvx_tool_venv() detection
# ---------------------------------------------------------------------------


def test_is_uvx_tool_venv_false_in_docker(
    _allow_real_uvx_detection, monkeypatch, tmp_path
):
    """Docker short-circuit: even with no pip + uv venv path, container = False.

    The wet Docker image uses ``uv sync`` which produces a venv WITHOUT
    pip. Without the Docker short-circuit, that signal would trip the
    pip-missing fallback and incorrectly reject SearXNG-dependent actions
    inside Method 3 stdio Docker (where Docker daemon access enables
    SearXNG via the host socket mount).
    """
    # Inside Docker, even pip-missing AND uv tools path must NOT be detected
    # as a uvx tool venv.
    fake_exe = tmp_path / "app" / ".venv" / "bin" / "python"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: None)
    # Simulate /.dockerenv presence — the standard Docker container marker.
    monkeypatch.setattr(tc, "_is_in_docker", lambda: True)

    assert tc.is_uvx_tool_venv() is False


def test_is_uvx_tool_venv_false_in_http_mode(
    _allow_real_uvx_detection, monkeypatch, tmp_path
):
    """HTTP transport short-circuit: even with no pip AND no /.dockerenv marker
    (the Cloudflare Containers case), HTTP mode must NOT be detected as uvx.

    CF Containers run the ``uv sync`` image via a non-Docker runtime that omits
    ``/.dockerenv``, so the no-pip fallback would otherwise wrongly reject
    SearXNG actions there. The ``MCP_TRANSPORT=http`` signal keeps them allowed.
    """
    fake_exe = tmp_path / "app" / ".venv" / "bin" / "python"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.delenv("TRANSPORT_MODE", raising=False)

    assert tc.is_uvx_tool_venv() is False


def test_is_uvx_tool_venv_true_when_executable_under_uv_tools(
    _allow_real_uvx_detection, monkeypatch, tmp_path
):
    """``sys.executable`` containing ``uv/tools/`` triggers detection."""
    fake_exe = tmp_path / "uv" / "tools" / "wet" / "Scripts" / "python.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    # Force not-in-Docker so the path-based signal can fire.
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    # Pretend pip *is* importable so the path check is the only signal.
    monkeypatch.setattr(
        tc.importlib.util, "find_spec", lambda name: object() if name == "pip" else None
    )

    assert tc.is_uvx_tool_venv() is True


def test_is_uvx_tool_venv_true_when_pip_missing(
    _allow_real_uvx_detection, monkeypatch, tmp_path
):
    """``find_spec('pip') is None`` triggers detection on its own."""
    # Path does NOT contain uv/tools.
    fake_exe = tmp_path / "normal" / "venv" / "bin" / "python"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: None)

    assert tc.is_uvx_tool_venv() is True


def test_is_uvx_tool_venv_false_for_normal_venv(
    _allow_real_uvx_detection, monkeypatch, tmp_path
):
    """Normal venv with pip installed and no uv/tools path -> False."""
    fake_exe = tmp_path / "project" / ".venv" / "bin" / "python"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setattr(
        tc.importlib.util, "find_spec", lambda name: object() if name == "pip" else None
    )

    assert tc.is_uvx_tool_venv() is False


def test_is_uvx_tool_venv_memoizes(_allow_real_uvx_detection, monkeypatch, tmp_path):
    """Result is cached after the first call."""
    fake_exe = tmp_path / "uv" / "tools" / "wet" / "bin" / "python"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setattr(
        tc.importlib.util, "find_spec", lambda name: object() if name == "pip" else None
    )

    first = tc.is_uvx_tool_venv()

    # Flip both signals; cached result must persist.
    monkeypatch.setattr(sys, "executable", str(tmp_path / "other" / "python"))
    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: None)

    second = tc.is_uvx_tool_venv()
    assert first == second is True


# ---------------------------------------------------------------------------
# search() short-circuit on uvx detection
# ---------------------------------------------------------------------------


def _force_uvx(monkeypatch, value: bool):
    """Force ``is_uvx_tool_venv`` to return ``value`` in every live binding.

    ``test_server_timeout.py`` deletes and reimports ``wet.server``
    under heavy mocking, so two distinct copies of that module can coexist
    in ``sys.modules`` for the rest of the run. Patch every copy reachable
    from ``sys.modules`` (and ``transport_check``) and return the freshly
    resolved module so tests use the live version.
    """
    import sys

    monkeypatch.setattr(tc, "is_uvx_tool_venv", lambda: value)
    if "wet.server" not in sys.modules:
        import wet.server  # noqa: F401
    srv = sys.modules["wet.server"]
    monkeypatch.setattr(srv, "is_uvx_tool_venv", lambda: value)
    return srv


@pytest.mark.parametrize("action", ["search", "research", "docs", "similar"])
@pytest.mark.asyncio
async def test_search_actions_rejected_in_uvx_mode(monkeypatch, action):
    """All four SearXNG-dependent actions return the spec error in uvx when no
    backend can run there (an explicit ``searxng``-only chain on the local
    auto-spawn URL, no cloud key, no external SearXNG)."""
    srv = _force_uvx(monkeypatch, True)
    # Clear ambient env so only the local-only chain below is configured,
    # regardless of what's set in the developer's shell.
    for var in (
        "SEARCH_BACKEND",
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
        "EXA_API_KEY",
        "SEARXNG_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng")

    # ``docs`` requires ``library``; ``similar`` requires a URL query. Pass
    # values that would normally make it past input validation so we know
    # the rejection comes from the uvx gate, not from missing parameters.
    kwargs = {"query": "https://example.com"}
    if action == "docs":
        kwargs["library"] = "fastapi"

    result = await srv.search(action=action, **kwargs)

    assert payload(result)["error"].startswith(
        f"Error: action '{action}' needs a search backend"
    )
    assert "TAVILY_API_KEY" in text(result)
    assert "SEARXNG_URL=" in text(result)
    assert "docker build --target stdio -t wet:local ." in text(result)


@pytest.mark.asyncio
async def test_search_action_proceeds_when_not_uvx(monkeypatch):
    """In a normal venv, ``search`` reaches the configured provider chain."""
    srv = _force_uvx(monkeypatch, False)

    with patch.object(
        srv,
        "_run_configured_search",
        new_callable=AsyncMock,
        return_value=(
            '{"results": [{"url": "https://e", "title": "T", "snippet": "Search Results"}], '
            '"total": 1, "query": "hello world"}'
        ),
    ) as mock_search:
        result = await srv.search(action="search", query="hello world")

        assert "Search Results" in text(result)
        mock_search.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_proceeds_in_uvx_with_zero_config(monkeypatch):
    """uvx=True + no search config at all -> the guard lets 'search' through.

    The unset chain is the external ``tavily,keenable,firecrawl`` default and
    Keenable/Firecrawl need no key, so a pip-less venv must never be told to set
    one up.
    """
    from wet.config import Settings

    srv = _force_uvx(monkeypatch, True)
    for var in ("SEARCH_BACKENDS", "SEARCH_BACKEND", "TAVILY_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        srv.search_backends, "settings", Settings(_env_file=None), raising=True
    )

    with patch.object(
        srv.search_backends,
        "run_search_chain",
        new_callable=AsyncMock,
        return_value=(
            '{"results": [{"url": "https://e", "title": "T", "snippet": "s"}], '
            '"total": 1, "query": "hello"}'
        ),
    ) as mock_chain:
        result = await srv.search(action="search", query="hello")

    assert "needs a search backend" not in text(result)
    mock_chain.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_proceeds_in_uvx_with_cloud_key(monkeypatch):
    """uvx=True + a cloud key + SEARCH_BACKENDS listing it -> the guard no
    longer blocks 'search'/'research'/'similar'; each reaches its own
    downstream logic instead of the uvx-blocked error."""
    srv = _force_uvx(monkeypatch, True)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")

    fake_result = json.dumps(
        {
            "results": [{"url": "https://e", "title": "T", "snippet": "s"}],
            "total": 1,
            "query": "hello",
        }
    )

    # search: chain is tavily-only (no "searxng" leg), so it skips
    # ensure_searxng and hits run_search_chain directly.
    with patch.object(
        srv.search_backends, "run_search_chain", new_callable=AsyncMock
    ) as mock_chain:
        mock_chain.return_value = fake_result
        result = await srv.search(action="search", query="hello")
    assert "needs a search backend" not in text(result)
    mock_chain.assert_called_once()

    # research: routes through _do_research, mocked directly.
    with patch.object(srv, "_do_research", new_callable=AsyncMock) as mock_research:
        mock_research.return_value = fake_result
        result = await srv.search(action="research", query="hello")
    assert "needs a search backend" not in text(result)
    mock_research.assert_called_once()

    # similar: architecturally SearXNG-only (search_strategies.find_similar
    # doesn't go through the pluggable chain); the guard just needs to let
    # it through -- downstream ensure_searxng/find_similar are mocked so the
    # test stays fast and deterministic.
    with (
        patch.object(srv, "ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch(
            "wet.sources.search_strategies.find_similar", new_callable=AsyncMock
        ) as mock_similar,
    ):
        mock_ensure.return_value = "http://localhost:41592"
        mock_similar.return_value = fake_result
        result = await srv.search(action="similar", query="https://example.com/article")
    assert "needs a search backend" not in text(result)
    mock_similar.assert_called_once()


@pytest.mark.asyncio
async def test_search_proceeds_in_uvx_with_external_searxng(monkeypatch):
    """uvx=True + an external SEARXNG_URL -> the guard lets 'search' through.

    The chain default is external (tavily,duckduckgo) since the project retired
    its own SearXNG instance, so a searxng-only chain is now explicit.
    """
    srv = _force_uvx(monkeypatch, True)
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng")
    monkeypatch.delenv("SEARCH_BACKEND", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "https://searxng.example.com")

    with (
        patch.object(srv, "ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch("wet.sources.searxng.search", new_callable=AsyncMock) as mock_search,
    ):
        mock_ensure.return_value = "https://searxng.example.com"
        mock_search.return_value = (
            '{"results": [{"url": "https://e", "title": "T", "snippet": "Search Results"}], '
            '"total": 1, "query": "hello world"}'
        )

        result = await srv.search(action="search", query="hello world")

        assert "needs a search backend" not in text(result)
        assert "Search Results" in text(result)
        # An external URL needs no local spawn, and auto-start is off by default.
        mock_ensure.assert_not_called()


@pytest.mark.asyncio
async def test_extract_action_works_regardless_of_uvx(monkeypatch):
    """``extract`` action stays available in uvx mode (no SearXNG dep)."""
    srv = _force_uvx(monkeypatch, True)

    with patch.object(srv, "_extract", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = "Extracted Content"

        result = await srv.extract(action="extract", urls=["https://example.com"])

        assert "Extracted Content" in text(result)
        mock_extract.assert_called_once()


def test_uvx_searxng_blocked_error():
    """uvx_searxng_blocked_error() formats the message correctly, listing all
    three copy-paste-able options (cloud key / external SearXNG / Docker)."""
    result = tc.uvx_searxng_blocked_error("search")
    assert "Error: action 'search' needs a search backend" in result
    assert "TAVILY_API_KEY" in result
    assert "SEARXNG_URL=" in result
    assert "docker build --target stdio -t wet:local ." in result
    assert "https://github.com/n24q02m/wet#setup" in result


# ---------------------------------------------------------------------------
# has_uvx_runnable_backend() -- block/allow matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chain,env,expected",
    [
        ([], {}, False),
        (["searxng"], {}, False),
        (["searxng"], {"SEARXNG_URL": "https://searxng.example.com"}, True),
        (["tavily"], {}, False),
        (["tavily"], {"TAVILY_API_KEY": "tvly-key"}, True),
        (["brave"], {"BRAVE_API_KEY": "brave-key"}, True),
        (["exa"], {"EXA_API_KEY": "exa-key"}, True),
        (["searxng", "tavily"], {"TAVILY_API_KEY": "tvly-key"}, True),
    ],
)
def test_has_uvx_runnable_backend(monkeypatch, chain, env, expected):
    """Block/allow matrix from the E0.1 spec: cloud keys and an external
    SearXNG URL make a chain uvx-runnable; the local-only default does not."""
    import wet.sources.search_backends as sb

    for var in ("TAVILY_API_KEY", "BRAVE_API_KEY", "EXA_API_KEY", "SEARXNG_URL"):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sb, "chain_backend_names", lambda: chain)

    assert sb.has_uvx_runnable_backend() is expected


# ---------------------------------------------------------------------------
# The memoized public entry point and its raw signals
# ---------------------------------------------------------------------------

# Captured at import, before the autouse conftest stub replaces the attribute,
# so the real memoizing wrapper can be exercised.
_REAL_IS_UVX_TOOL_VENV = tc.is_uvx_tool_venv


def test_real_entry_point_memoizes_until_reset(monkeypatch, tmp_path):
    """The first answer is cached for the process; only ``reset_cache``
    makes the next call look at the signals again."""
    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setattr(tc, "_is_http_transport", lambda: False)
    monkeypatch.setattr(
        sys, "executable", str(tmp_path / "uv" / "tools" / "wet" / "python")
    )
    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: object())
    tc.reset_cache()
    try:
        assert _REAL_IS_UVX_TOOL_VENV() is True

        monkeypatch.setattr(sys, "executable", str(tmp_path / "venv" / "python"))
        assert _REAL_IS_UVX_TOOL_VENV() is True

        tc.reset_cache()
        assert _REAL_IS_UVX_TOOL_VENV() is False
    finally:
        tc.reset_cache()


def test_docker_marker_is_the_dockerenv_file(monkeypatch):
    """Docker detection asks for exactly ``/.dockerenv``."""
    asked = []
    monkeypatch.setattr(tc.os.path, "exists", lambda p: asked.append(p) or True)

    assert tc._is_in_docker() is True
    assert asked == ["/.dockerenv"]


def test_unresolvable_executable_falls_back_to_the_pip_signal(monkeypatch):
    """An interpreter path that cannot be resolved is not an error: detection
    falls through to the pip check."""

    class _Unresolvable:
        def __init__(self, raw):
            pass

        def resolve(self):
            raise OSError("broken symlink loop")

    monkeypatch.setattr(tc, "_is_in_docker", lambda: False)
    monkeypatch.setattr(tc, "_is_http_transport", lambda: False)
    monkeypatch.setattr(tc, "Path", _Unresolvable)

    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: object())
    assert tc._detect_uvx_tool_venv() is False

    monkeypatch.setattr(tc.importlib.util, "find_spec", lambda name: None)
    assert tc._detect_uvx_tool_venv() is True
