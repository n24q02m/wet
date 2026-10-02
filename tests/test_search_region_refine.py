"""W2-2: optional ``region`` geo filter + opt-in bounded refinement.

Covers:
- region plumbing per backend (SearXNG locale mapping, Tavily country enum,
  Brave ``country`` param) including explicit structured errors naming a
  backend that cannot honor the region;
- the chain-level rule: unsupported backends are skipped (named), and a chain
  with no region-capable backend returns a structured error;
- refine=True: max 2 review rounds, LLM-rewritten re-queries only when the
  quality gate fails, best round wins, provenance preserved.
"""

import json
import unittest.mock

from structured import payload

from wet_mcp.sources.search_backends import (
    _TAVILY_COUNTRY_BY_ISO,
    BraveBackend,
    ExaBackend,
    SearxngBackend,
    TavilyBackend,
    _searxng_locale,
    run_search_chain,
)

# ---------------------------------------------------------------------------
# Region plumbing per backend
# ---------------------------------------------------------------------------


def test_searxng_locale_mapping():
    assert _searxng_locale("vi", "vn") == "vi-VN"
    assert _searxng_locale(None, "us") == "US"
    assert _searxng_locale("en", None) == "en"
    assert _searxng_locale(None, None) is None


async def test_searxng_region_plumbs_combined_locale():
    seen = {}

    async def fake_searxng_search(**kwargs):
        seen.update(kwargs)
        return json.dumps({"results": [], "total": 0, "query": kwargs["query"]})

    with unittest.mock.patch(
        "wet_mcp.sources.searxng.search", side_effect=fake_searxng_search
    ):
        await SearxngBackend("http://x").search("q", language="vi", region="vn")
    assert seen["language"] == "vi-VN"


async def test_tavily_region_maps_iso_to_country_enum():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(return_value={"results": []})
        post.return_value = resp
        await TavilyBackend(["k"]).search("q", region="US")
        body = post.call_args.kwargs["json"]
        assert body["country"] == "united states"


async def test_tavily_region_unknown_code_is_structured_error():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        out = json.loads(await TavilyBackend(["k"]).search("q", region="zz"))
        assert "tavily" in out["error"]
        assert "zz" in out["error"]
        post.assert_not_awaited()


async def test_tavily_no_region_omits_country():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(return_value={"results": []})
        post.return_value = resp
        await TavilyBackend(["k"]).search("q")
        assert "country" not in post.call_args.kwargs["json"]


async def test_brave_region_sets_country_param():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(return_value={"web": {"results": []}})
        get.return_value = resp
        await BraveBackend(["k"]).search("q", region="de")
        assert get.call_args.kwargs["params"]["country"] == "DE"


async def test_exa_region_returns_structured_error_naming_backend():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        out = json.loads(await ExaBackend(["k"]).search("q", region="US"))
        assert "exa" in out["error"]
        post.assert_not_awaited()


def test_tavily_country_table_is_complete_and_unique():
    assert len(_TAVILY_COUNTRY_BY_ISO) == 166
    assert len(set(_TAVILY_COUNTRY_BY_ISO.values())) == 166
    # spot checks against the provider enum
    assert _TAVILY_COUNTRY_BY_ISO["vn"] == "vietnam"
    assert _TAVILY_COUNTRY_BY_ISO["gb"] == "united kingdom"
    assert _TAVILY_COUNTRY_BY_ISO["kr"] == "south korea"


# ---------------------------------------------------------------------------
# Chain-level region handling (never a silent drop)
# ---------------------------------------------------------------------------


def _mock_backend(name, responder):
    b = unittest.mock.Mock()
    b.name = name
    b.search = unittest.mock.AsyncMock(side_effect=responder)
    return b


async def test_run_search_chain_region_skips_unsupported_backend_named(
    monkeypatch,
):
    monkeypatch.setenv("SEARCH_BACKENDS", "exa,brave")

    async def hit(**_kwargs):
        return json.dumps(
            {"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}
        )

    exa = _mock_backend("exa", hit)
    brave = _mock_backend("brave", hit)
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[exa, brave],
    ):
        out = json.loads(await run_search_chain("q", region="US"))

    assert out["results"][0]["url"] == "https://h/1"
    exa.search.assert_not_awaited()
    assert out["search_backend"]["attempted"] == ["brave"]


async def test_run_search_chain_region_all_unsupported_is_structured_error(
    monkeypatch,
):
    monkeypatch.setenv("SEARCH_BACKENDS", "exa")

    async def hit(**_kwargs):
        return json.dumps(
            {"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}
        )

    exa = _mock_backend("exa", hit)
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[exa],
    ):
        out = json.loads(await run_search_chain("q", region="US"))

    assert out["results"] == []
    assert "exa" in out["error"]
    assert "US" in out["error"]
    exa.search.assert_not_awaited()
    assert out["search_backend"]["fallback"] == "unavailable"


async def test_run_search_chain_region_reaches_capable_backend(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "brave")
    seen = {}

    async def hit(**kwargs):
        seen.update(kwargs)
        return json.dumps(
            {"results": [{"url": "https://h/1"}], "total": 1, "query": "q"}
        )

    brave = _mock_backend("brave", hit)
    with unittest.mock.patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[brave],
    ):
        out = json.loads(await run_search_chain("q", region="vn"))

    assert out["results"][0]["url"] == "https://h/1"
    assert brave.search.call_args.kwargs["region"] == "vn"


# ---------------------------------------------------------------------------
# refine=True: bounded iterative refinement
# ---------------------------------------------------------------------------


def _chain_mock(responses):
    """Async fake run_search_chain recording queries, returning canned JSON."""
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs["query"])
        return json.dumps(
            {
                "results": responses[min(len(calls), len(responses)) - 1],
                "total": len(responses[min(len(calls), len(responses)) - 1]),
                "query": kwargs["query"],
            },
            ensure_ascii=False,
        )

    return fake, calls


async def _call_search(**overrides):
    from wet_mcp.server import search

    return await search(action="search", query="python tutorial", **overrides)


def _patch_chain(fake):
    return unittest.mock.patch("wet_mcp.sources.search_backends.run_search_chain", fake)


def _patch_rewrite(side_effect):
    return unittest.mock.patch(
        "wet_mcp.sources.search_strategies.rewrite_query",
        unittest.mock.AsyncMock(side_effect=side_effect),
    )


async def test_refine_requeries_on_empty_with_rewritten_terms(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    empty: list = []
    hit = [{"url": "https://e/1", "title": "R1", "snippet": "s", "score": 0.9}]
    fake, calls = _chain_mock([empty, hit])
    with _patch_chain(fake), _patch_rewrite(["better python tutorial"]):
        result = await _call_search(refine=True)
    out = payload(result)
    assert len(calls) == 2
    assert calls[1] == "better python tutorial"
    assert out["results"][0]["url"] == "https://e/1"
    assert "error" not in out


async def test_refine_bound_max_two_review_rounds(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([[], [], []])
    with _patch_chain(fake), _patch_rewrite(["r1", "r2", "r3"]):
        result = await _call_search(refine=True)
    out = payload(result)
    # initial round + at most 2 review rounds, however eager the rewriter is
    assert len(calls) == 3
    assert out["results"] == []
    assert "error" not in out  # valid-empty, not an error


async def test_refine_stops_when_rewrite_unavailable(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([[]])
    with _patch_chain(fake), _patch_rewrite([None]):
        result = await _call_search(refine=True)
    out = payload(result)
    assert len(calls) == 1
    assert out["results"] == []
    assert "error" not in out


async def test_refine_skipped_when_quality_gate_passes(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    good = [{"url": "https://e/1", "title": "R1", "snippet": "s", "score": 0.9}]
    fake, calls = _chain_mock([good])
    rewrite = unittest.mock.AsyncMock()
    with _patch_chain(fake), _patch_rewrite(rewrite):
        result = await _call_search(refine=True)
    out = payload(result)
    assert len(calls) == 1
    rewrite.assert_not_awaited()
    assert out["results"][0]["score"] == 0.9


async def test_refine_returns_best_round_with_provenance(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    weak = [{"url": "https://a/1", "title": "A", "snippet": "s", "score": 0.1}]
    better = [{"url": "https://b/1", "title": "B", "snippet": "s", "score": 0.9}]
    fake, calls = _chain_mock([weak, better])
    with _patch_chain(fake), _patch_rewrite(["refined q"]):
        result = await _call_search(refine=True)
    out = payload(result)
    assert len(calls) == 2
    top = out["results"][0]
    assert top["url"] == "https://b/1"
    assert top["score"] == 0.9
    # provenance fields survive the round switch (standardize ran on winner)
    assert top["source_domain"] == "b"
    assert top["freshness_signal"] in ("fresh", "stale")


async def test_no_refine_keeps_single_round(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([[]])
    rewrite = unittest.mock.AsyncMock()
    with _patch_chain(fake), _patch_rewrite(rewrite):
        result = await _call_search()
    out = payload(result)
    assert len(calls) == 1
    rewrite.assert_not_awaited()
    assert out["results"] == []


# ---------------------------------------------------------------------------
# Param validation
# ---------------------------------------------------------------------------


async def test_region_param_error_is_structured(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    result = await _call_search(region="usa")
    out = payload(result)
    assert "error" in out
    assert "region" in out["error"]


async def test_region_normalized_uppercase_in_plumbing(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "brave")
    seen = {}

    async def hit(**kwargs):
        seen.update(kwargs)
        return json.dumps(
            {
                "results": [{"url": "https://h/1", "title": "H", "snippet": "s"}],
                "total": 1,
                "query": "q",
            }
        )

    with _patch_chain(hit):
        result = await _call_search(region="vn")
    out = payload(result)
    assert seen["region"] == "VN"
    assert out["results"][0]["url"] == "https://h/1"
