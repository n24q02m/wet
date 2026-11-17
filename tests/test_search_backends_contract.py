"""Request shaping, error envelopes and factory rules of the search backends.

Only the HTTP boundary (``httpx.AsyncClient.get`` / ``post``) is stubbed; the
credential pool behind the keyed backends is the real one, isolated per test
by the autouse ``_isolate_home`` fixture.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from wet.config import settings
from wet.sources import search_backends as sb


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


# ---------------------------------------------------------------------------
# Brave / Exa request shaping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "time_range,freshness", [("week", "pw"), ("year", "py"), ("decade", None)]
)
async def test_brave_maps_time_range_to_freshness_and_forwards_language(
    time_range, freshness
):
    """Known ranges become Brave's freshness codes; an unknown range is
    dropped rather than sent through verbatim."""
    sent: dict = {}

    async def fake_get(self, url, *, params, headers):
        sent.update(params)
        return _ok({"web": {"results": []}})

    with patch("httpx.AsyncClient.get", fake_get):
        await sb.BraveBackend(["k"]).search("q", time_range=time_range, language="vi")

    assert sent.get("freshness") == freshness
    assert sent["search_lang"] == "vi"


async def test_exa_forwards_domain_filters():
    sent: dict = {}

    async def fake_post(self, url, *, json, headers):
        sent.update(json)
        return _ok({"results": []})

    with patch("httpx.AsyncClient.post", fake_post):
        await sb.ExaBackend(["k"]).search(
            "q", include_domains=["docs.python.org"], exclude_domains=["spam.com"]
        )

    assert sent["includeDomains"] == ["docs.python.org"]
    assert sent["excludeDomains"] == ["spam.com"]


async def test_exa_http_failure_is_an_error_envelope_without_the_key():
    async def fake_post(self, url, json=None, headers=None):
        return httpx.Response(400, text="bad request for key exa-secret")

    with patch("httpx.AsyncClient.post", fake_post):
        out = await sb.ExaBackend(["exa-secret"]).search("q")

    assert json.loads(out) == {"error": "Exa HTTP 400"}
    assert "exa-secret" not in out


# ---------------------------------------------------------------------------
# Keyed rotation and keyless error envelopes
# ---------------------------------------------------------------------------


async def test_keyed_backend_without_keys_says_so():
    out = await sb.BraveBackend([]).search("q")

    assert json.loads(out) == {"error": "Brave search backend has no API key"}


async def test_every_key_rejected_exhausts_the_pool_with_the_last_error():
    """Two keys, both 401: both get disabled and the caller receives the
    provider's last (redacted) error instead of an exception."""
    used: list[str] = []

    async def fake_post(self, url, **kwargs):
        used.append(kwargs["json"]["api_key"])
        return httpx.Response(401, text="unauthorized")

    with patch("httpx.AsyncClient.post", fake_post):
        out = await sb.TavilyBackend(["tv-a", "tv-b"]).search("q")

    assert sorted(used) == ["tv-a", "tv-b"]
    error = json.loads(out)["error"]
    assert "401" in error
    assert "tv-a" not in out and "tv-b" not in out


@pytest.mark.parametrize(
    "raised,expected",
    [
        (httpx.ConnectError("boom"), "DuckDuckGo request failed: ConnectError"),
        (UnicodeDecodeError("utf-8", b"", 0, 1, "x"), "DuckDuckGo search failed"),
    ],
)
async def test_keyless_backend_failures_become_error_envelopes(raised, expected):
    """A credential-free backend never raises to the chain: transport errors
    and anything else become type-named error envelopes."""
    with patch("httpx.AsyncClient.post", AsyncMock(side_effect=raised)):
        out = await sb.DuckDuckGoBackend().search("q")

    assert json.loads(out)["error"].startswith(expected)


# ---------------------------------------------------------------------------
# Factory: explicit SEARCH_BACKEND
# ---------------------------------------------------------------------------


@pytest.fixture
def explicit_backend(monkeypatch):
    """Select a backend by name with no key from env or settings."""
    for var in ("SEARCH_BACKENDS", "BRAVE_API_KEY", "EXA_API_KEY", "KAGI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    for attr in ("brave_api_key", "exa_api_key", "kagi_api_key", "searxng_url"):
        monkeypatch.setattr(settings, attr, "", raising=False)
    monkeypatch.setattr(settings, "search_backends", "", raising=False)

    def select(name: str) -> None:
        monkeypatch.setenv("SEARCH_BACKEND", name)
        monkeypatch.setattr(settings, "search_backend", name, raising=False)

    return select


@pytest.mark.parametrize(
    "name,env,cls",
    [
        ("brave", "BRAVE_API_KEY", sb.BraveBackend),
        ("exa", "EXA_API_KEY", sb.ExaBackend),
        ("kagi", "KAGI_API_KEY", sb.KagiBackend),
    ],
)
def test_explicit_keyed_backend_needs_its_key(
    explicit_backend, monkeypatch, name, env, cls
):
    """Without its key the named backend refuses to build (naming the env
    var); with a CSV of keys it carries every key for rotation."""
    explicit_backend(name)
    with pytest.raises(ValueError, match=env):
        sb.search_backend_from_env()

    monkeypatch.setenv(env, "key-1, key-2")
    backend = sb.search_backend_from_env()

    assert isinstance(backend, cls)
    assert backend.keys == ["key-1", "key-2"]


def test_explicit_searxng_without_url_refuses(explicit_backend):
    explicit_backend("searxng")

    with pytest.raises(ValueError, match="SEARXNG_URL required"):
        sb.search_backend_from_env()


def test_unknown_backend_name_is_rejected(explicit_backend):
    explicit_backend("bing")

    with pytest.raises(ValueError, match="Unknown search backend: bing"):
        sb.search_backend_from_env()


# ---------------------------------------------------------------------------
# Parallel fan-out edge cases
# ---------------------------------------------------------------------------


def _backend(name: str, outcome: str) -> Mock:
    backend = Mock()
    backend.name = name
    backend.search = AsyncMock(return_value=outcome)
    return backend


async def _fan_out(*backends: Mock) -> dict:
    with (
        patch.object(
            sb, "search_backends_with_skips", return_value=(list(backends), {})
        ),
        patch.object(
            sb, "chain_backend_names", return_value=[b.name for b in backends]
        ),
    ):
        return json.loads(await sb.run_search_chain("q", parallel=True))


async def test_parallel_fanout_with_only_failures_reports_exhaustion():
    """An error envelope and a malformed payload: no results, and the
    envelope says the chain failed instead of looking like an empty search."""
    out = await _fan_out(
        _backend("tavily", json.dumps({"error": "tavily HTTP 500"})),
        _backend("brave", "<html>gateway</html>"),
    )

    assert out["results"] == []
    assert out["error"] == "Search backend chain exhausted after provider failure"
    assert out["search_backend"]["fallback"] == "exhausted"
    assert out["search_backend"]["selected"] is None


async def test_parallel_fanout_keeps_upstream_source_and_drops_non_objects():
    """A result that already names its source keeps it; a non-object entry
    in a backend's list is ignored."""
    out = await _fan_out(
        _backend(
            "searxng",
            json.dumps(
                {
                    "results": [
                        "not-a-result",
                        {"url": "https://a.com", "title": "A", "source": "google"},
                    ]
                }
            ),
        ),
        _backend("brave", json.dumps({"results": []})),
    )

    assert out["results"] == [
        {"url": "https://a.com", "title": "A", "source": "google"}
    ]
    assert "error" not in out
    assert out["search_backend"]["selected"] == "searxng"
