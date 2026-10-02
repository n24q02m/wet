import json
import unittest.mock

import httpx
import pytest
from structured import text

from wet_mcp.sources.search_backends import (
    BraveBackend,
    ExaBackend,
    SearxngBackend,
    TavilyBackend,
    _search_result_is_empty,
    chain_backend_names,
    run_search_chain,
    search_backend_from_env,
    search_backends_from_env,
)


async def test_tavily_maps_rest_response():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(
            return_value={
                "results": [{"url": "https://e/1", "title": "R1", "content": "c1"}]
            }
        )
        post.return_value = resp
        out = json.loads(await TavilyBackend(["k"]).search("q", max_results=1))
        assert out["total"] == 1
        assert out["query"] == "q"
        assert out["results"][0]["url"] == "https://e/1"
        assert "snippet" in out["results"][0]


async def test_tavily_http_error_returns_error_json():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 401
        post.return_value = resp
        out = json.loads(await TavilyBackend(["bad"]).search("q"))
        assert "error" in out


def test_factory_defaults_to_searxng(monkeypatch):
    monkeypatch.delenv("SEARCH_BACKEND", raising=False)
    assert isinstance(search_backend_from_env(), SearxngBackend)


def test_factory_tavily_requires_key(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        search_backend_from_env()


async def test_server_search_routes_through_chain(monkeypatch):
    # A non-searxng chain avoids the embedded SearXNG spawn; run_search_chain is
    # the single integration point the server now calls.
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake_chain = unittest.mock.AsyncMock(
        return_value='{"results": [{"url": "https://e/1", "title": "R1", "snippet": "s"}], "total": 1, "query": "q"}'
    )
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.run_search_chain", fake_chain
    ):
        from wet_mcp.server import search

        result = await search(action="search", query="python tutorial", max_results=5)
        assert "results" in text(result)
        fake_chain.assert_awaited()


async def test_tavily_error_never_leaks_api_key():
    secret = "tvly-SECRET-DEADBEEF"
    with unittest.mock.patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectError(
            "connect failed url=https://api.tavily.com/search "
            "body={'api_key': 'tvly-SECRET-DEADBEEF'}"
        ),
    ):
        out = await TavilyBackend([secret]).search("q")
    assert secret not in out
    assert "error" in json.loads(out)


async def test_server_search_tavily_missing_key_degrades_gracefully(monkeypatch):
    # New chain behaviour: a backend whose key is missing is SKIPPED; when the
    # whole chain is empty the result is a clear (non-fatal) "missing API keys"
    # envelope rather than the old hard "Error: TAVILY_API_KEY required".
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "", raising=False)
    monkeypatch.setattr(settings, "search_backends", "tavily", raising=False)
    from wet_mcp.server import search

    # The search action wraps results in untrusted-content guards, so assert on
    # substrings rather than parsing.
    result = await search(action="search", query="python tutorial")
    assert "missing API keys" in text(result)
    assert "tavily" in text(result)


# ---------------------------------------------------------------------------
# Brave + Exa backends
# ---------------------------------------------------------------------------


async def test_brave_maps_web_results():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(
            return_value={
                "web": {
                    "results": [
                        {"url": "https://b/1", "title": "B1", "description": "d1"}
                    ]
                }
            }
        )
        get.return_value = resp
        out = json.loads(await BraveBackend(["k"]).search("q", max_results=1))
        assert out["total"] == 1
        assert out["results"][0]["url"] == "https://b/1"
        assert out["results"][0]["snippet"] == "d1"
        assert out["results"][0]["source"] == "brave"


async def test_brave_http_error_returns_error_json():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 429
        get.return_value = resp
        assert "error" in json.loads(await BraveBackend(["k"]).search("q"))


async def test_brave_error_never_leaks_key():
    secret = "brave-test-token-not-real"  # noqa: S105 - low-entropy fake for leak test
    with unittest.mock.patch(
        "httpx.AsyncClient.get",
        side_effect=httpx.ConnectError(f"failed token={secret}"),
    ):
        out = await BraveBackend([secret]).search("q")
    assert secret not in out


async def test_exa_maps_results_with_text_snippet():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(
            return_value={
                "results": [{"url": "https://x/1", "title": "X1", "text": "y" * 500}]
            }
        )
        post.return_value = resp
        out = json.loads(await ExaBackend(["k"]).search("q", max_results=1))
        assert out["results"][0]["source"] == "exa"
        assert len(out["results"][0]["snippet"]) == 300  # truncated


# ---------------------------------------------------------------------------
# Chain resolution + runtime fallback
# ---------------------------------------------------------------------------


def test_chain_backend_names_csv(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng, tavily , brave")
    assert chain_backend_names() == ["searxng", "tavily", "brave"]


def test_chain_falls_back_to_single_backend(monkeypatch):
    monkeypatch.delenv("SEARCH_BACKENDS", raising=False)
    monkeypatch.setenv("SEARCH_BACKEND", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "search_backends", "", raising=False)
    assert chain_backend_names() == ["tavily"]


def test_chain_skips_missing_key_backends(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily,searxng")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "search_backends", "tavily,searxng", raising=False)
    monkeypatch.setattr(settings, "tavily_api_key", "", raising=False)
    backends = search_backends_from_env()
    # tavily skipped (no key); only searxng remains.
    assert len(backends) == 1
    assert isinstance(backends[0], SearxngBackend)


def test_search_result_is_empty_predicate():
    assert _search_result_is_empty('{"error": "boom"}') is True
    assert _search_result_is_empty('{"results": []}') is True
    assert _search_result_is_empty("not json") is True
    assert _search_result_is_empty('{"results": [{"url": "x"}]}') is False


async def test_run_search_chain_falls_back_on_empty(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng,brave")
    # First backend returns empty, second returns a hit -> second wins.
    empty = unittest.mock.AsyncMock(
        return_value='{"results": [], "total": 0, "query": "q"}'
    )
    hit = unittest.mock.AsyncMock(
        return_value='{"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}'
    )
    b0 = unittest.mock.Mock()
    b0.name = "searxng"
    b0.search = empty
    b1 = unittest.mock.Mock()
    b1.name = "brave"
    b1.search = hit
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b0, b1],
    ):
        out = json.loads(await run_search_chain("q"))
        assert out["results"][0]["url"] == "https://h/1"
        assert out["search_backend"] == {
            "requested": ["searxng", "brave"],
            "attempted": ["searxng", "brave"],
            "selected": "brave",
            "fallback": "used",
        }
        empty.assert_awaited()
        hit.assert_awaited()


async def test_run_search_chain_all_empty_is_legitimate_empty(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng,brave")
    empty = unittest.mock.AsyncMock(
        return_value='{"results": [], "total": 0, "query": "q"}'
    )
    b0 = unittest.mock.Mock()
    b0.name = "searxng"
    b0.search = empty
    b1 = unittest.mock.Mock()
    b1.name = "brave"
    b1.search = empty
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b0, b1],
    ):
        out = json.loads(await run_search_chain("q"))

    assert out["results"] == []
    assert "error" not in out
    assert out["search_backend"]["fallback"] == "exhausted"


async def test_run_search_chain_reports_error_when_all_backends_fail(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng,brave")
    failed = unittest.mock.AsyncMock(side_effect=RuntimeError("provider down"))
    b0 = unittest.mock.Mock()
    b0.name = "searxng"
    b0.search = failed
    b1 = unittest.mock.Mock()
    b1.name = "brave"
    b1.search = failed
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b0, b1],
    ):
        out = json.loads(await run_search_chain("q"))

    assert out["results"] == []
    assert out["error"] == "Search backend chain exhausted after provider failure"


async def test_run_search_chain_advances_past_non_list_results(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng,brave")
    malformed = unittest.mock.AsyncMock(
        return_value='{"results": "not-a-list", "total": 1, "query": "q"}'
    )
    hit = unittest.mock.AsyncMock(
        return_value='{"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}'
    )
    b0 = unittest.mock.Mock()
    b0.name = "searxng"
    b0.search = malformed
    b1 = unittest.mock.Mock()
    b1.name = "brave"
    b1.search = hit
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b0, b1],
    ):
        out = json.loads(await run_search_chain("q"))

    assert out["results"][0]["url"] == "https://h/1"
    assert out["search_backend"]["selected"] == "brave"
    assert out["search_backend"]["fallback"] == "used"


async def test_run_search_chain_reports_skipped_configured_backend_as_fallback(
    monkeypatch,
):
    monkeypatch.setenv("SEARCH_BACKENDS", "brave,searxng")

    async def hit(**_kwargs):
        return json.dumps(
            {"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}
        )

    backend = unittest.mock.Mock()
    backend.name = "searxng"
    backend.search = hit
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[backend],
    ):
        out = json.loads(await run_search_chain("q"))

    assert out["search_backend"] == {
        "requested": ["brave", "searxng"],
        "attempted": ["searxng"],
        "selected": "searxng",
        "fallback": "used",
    }


async def test_run_search_chain_empty_when_no_backends(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "brave")
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "search_backends", "brave", raising=False)
    monkeypatch.setattr(settings, "brave_api_key", "", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    out = json.loads(await run_search_chain("q"))
    assert out["results"] == []
    assert "brave" in out["error"]
    assert out["search_backend"] == {
        "requested": ["brave"],
        "attempted": [],
        "selected": None,
        "fallback": "unavailable",
    }
