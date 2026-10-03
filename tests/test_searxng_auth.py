"""wet reads SEARXNG_AUTH_USER/PASS and applies HTTP basic-auth to the external
SearXNG (search + health check), instead of requiring credentials embedded in
SEARXNG_URL."""

from unittest.mock import AsyncMock, MagicMock, patch

import wet.sources.searxng as sx
from wet.config import settings


def _set_auth(monkeypatch, user, pwd):
    monkeypatch.setattr(settings, "searxng_auth_user", user, raising=False)
    monkeypatch.setattr(settings, "searxng_auth_pass", pwd, raising=False)


def test_searxng_auth_tuple_when_both_set(monkeypatch):
    _set_auth(monkeypatch, "u", "p")
    assert sx._searxng_auth() == ("u", "p")


def test_searxng_auth_none_when_partial_or_empty(monkeypatch):
    _set_auth(monkeypatch, "u", "")
    assert sx._searxng_auth() is None
    _set_auth(monkeypatch, "", "p")
    assert sx._searxng_auth() is None
    _set_auth(monkeypatch, "", "")
    assert sx._searxng_auth() is None


async def test_search_forwards_auth_to_hull_web(monkeypatch):
    _set_auth(monkeypatch, "u", "p")
    captured = {}

    async def fake_wc_search(url, query, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(
        sx, "_ensure_searxng_healthy", AsyncMock(return_value="http://sx")
    )
    monkeypatch.setattr(sx, "_wc_search", fake_wc_search)
    await sx.search("http://sx", "q")
    assert captured.get("auth") == ("u", "p")


async def test_search_auth_none_when_unset(monkeypatch):
    _set_auth(monkeypatch, "", "")
    captured = {}

    async def fake_wc_search(url, query, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(
        sx, "_ensure_searxng_healthy", AsyncMock(return_value="http://sx")
    )
    monkeypatch.setattr(sx, "_wc_search", fake_wc_search)
    await sx.search("http://sx", "q")
    assert captured.get("auth") is None


async def test_check_health_applies_auth(monkeypatch):
    _set_auth(monkeypatch, "u", "p")
    resp = MagicMock(status_code=200)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=client):
        ok = await sx._check_health("http://sx")
    assert ok is True
    assert client.get.call_args.kwargs.get("auth") == ("u", "p")


def _mock_health_client(status=None, exc=None):
    resp = MagicMock(status_code=status)
    client = MagicMock()
    client.get = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def test_check_health_reachable_on_2xx_4xx(monkeypatch):
    """A reachable instance (200 ready, or 401/403/404 up-but-gated) is healthy —
    an external SearXNG behind Caddy/CF auth answers /healthz 401/403 yet works, so
    treating it as unhealthy would trigger a pointless local-SearXNG restart/spawn."""
    _set_auth(monkeypatch, "", "")
    for code in (200, 401, 403, 404, 499):
        with patch("httpx.AsyncClient", return_value=_mock_health_client(status=code)):
            assert await sx._check_health("http://sx") is True, (
                f"{code} should be reachable"
            )


async def test_check_health_down_on_5xx_or_conn_error(monkeypatch):
    """5xx (server error) or a connection/timeout error means actually down."""
    import httpx

    _set_auth(monkeypatch, "", "")
    with patch("httpx.AsyncClient", return_value=_mock_health_client(status=503)):
        assert await sx._check_health("http://sx") is False
    with patch(
        "httpx.AsyncClient",
        return_value=_mock_health_client(exc=httpx.ConnectError("refused")),
    ):
        assert await sx._check_health("http://sx") is False
