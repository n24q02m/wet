"""Extended search backends: kagi, firecrawl, and the credential-free tier
(duckduckgo, startpage).

Unit tests mock ``httpx.AsyncClient`` and assert SHAPE (request form/headers,
HTML/JSON parsing, bot-challenge -> error envelope so the chain advances,
factory + uvx-runnability). No network access, no key material.
"""

import json
import unittest.mock
from urllib.parse import urlsplit

from wet_mcp.sources.search_backends import (
    DuckDuckGoBackend,
    FirecrawlBackend,
    KagiBackend,
    StartpageBackend,
    _make_backend,
    chain_backend_names,
    has_uvx_runnable_backend,
    run_search_chain,
    search_backends_from_env,
)

# --- fixtures ---------------------------------------------------------------

DDG_PAGE = """
<html><body>
<div class="results">
  <div class="result results_links">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=xyz">Title A &amp; more</a>
    <a class="result__snippet">Snippet <b>A</b> text</a>
  </div>
  <div class="result results_links">
    <a class="result__a" href="https://example.com/b">Title B</a>
    <div class="result__snippet">Snippet B</div>
  </div>
  <div class="result results_links">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=zzz">Title A dup</a>
  </div>
</div>
</body></html>
"""

DDG_ANOMALY_PAGE = '<html><body><div id="anomaly-modal">unusual traffic</div><script src="anomaly.js"></script></body></html>'

STARTPAGE_PAGE = """
<html><body>
<div class="result">
  <a class="result-link" href="https://example.com/x"><h2>Result X</h2></a>
  <p class="description">Desc X</p>
</div>
<div class="result">
  <a class="result-link" href="https://www.startpage.com/sp/search?query=nav">Internal nav</a>
</div>
<div class="result">
  <a class="result-link" href="https://example.com/y"><h3>Result Y</h3></a>
  <p class="description">Desc &amp; Y</p>
</div>
</body></html>
"""

STARTPAGE_CAPTCHA_PAGE = (
    "<html><body>Please complete the CAPTCHA to continue</body></html>"
)


def _resp(status_code=200, json_data=None, text=""):
    resp = unittest.mock.AsyncMock()
    resp.status_code = status_code
    resp.json = unittest.mock.Mock(return_value=json_data or {})
    resp.text = text
    return resp


# --- duckduckgo -------------------------------------------------------------


async def test_ddg_maps_results_and_unwraps_uddg_redirects():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(text=DDG_PAGE)
        out = json.loads(await DuckDuckGoBackend().search("q", max_results=10))
    assert [r["url"] for r in out["results"]] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert out["results"][0]["title"] == "Title A & more"
    assert out["results"][0]["snippet"] == "Snippet A text"
    assert out["results"][0]["source"] == "duckduckgo"
    # dedupe on unwrapped URL (third block repeats example.com/a)
    assert out["total"] == 2


async def test_ddg_bot_challenge_returns_error_envelope():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(text=DDG_ANOMALY_PAGE)
        out = json.loads(await DuckDuckGoBackend().search("q"))
    assert "error" in out  # safe "<Provider> HTTP <code>", chain advances


async def test_ddg_recency_maps_to_df_form_field():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(text=DDG_PAGE)
        await DuckDuckGoBackend().search("q", time_range="week")
        form = post.call_args.kwargs["data"]
    assert form["df"] == "w"
    assert form["q"] == "q"


# --- startpage --------------------------------------------------------------


async def test_startpage_maps_results_and_skips_internal_links():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        get.return_value = _resp(text=STARTPAGE_PAGE)
        out = json.loads(await StartpageBackend().search("q"))
    assert [r["url"] for r in out["results"]] == [
        "https://example.com/x",
        "https://example.com/y",
    ]
    assert out["results"][0]["title"] == "Result X"
    assert out["results"][1]["snippet"] == "Desc & Y"


async def test_startpage_captcha_returns_error_envelope():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        get.return_value = _resp(text=STARTPAGE_CAPTCHA_PAGE)
        out = json.loads(await StartpageBackend().search("q"))
    assert "error" in out


async def test_startpage_recency_maps_to_with_date_param():
    with unittest.mock.patch("httpx.AsyncClient.get") as get:
        get.return_value = _resp(text=STARTPAGE_PAGE)
        await StartpageBackend().search("q", time_range="day")
        params = get.call_args.kwargs["params"]
    assert params["with_date"] == "d"


# --- firecrawl --------------------------------------------------------------


async def test_firecrawl_maps_search_rows_and_sends_bearer_key():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(
            json_data={
                "success": True,
                "data": {
                    "search": [
                        {"url": "https://f/1", "title": "F1", "description": "d1"},
                        {"href": "https://f/2", "name": "F2", "summary": "d2"},
                    ]
                },
            }
        )
        out = json.loads(await FirecrawlBackend(["fc-k"]).search("q"))
        headers = post.call_args.kwargs["headers"]
        body = post.call_args.kwargs["json"]
    assert headers["Authorization"] == "Bearer fc-k"
    assert body["sources"] == [{"type": "web"}]
    assert body["limit"] == 10
    assert [r["url"] for r in out["results"]] == ["https://f/1", "https://f/2"]
    assert out["results"][1]["snippet"] == "d2"


async def test_firecrawl_keyless_omits_authorization():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(json_data={"success": True, "data": {"search": []}})
        out = json.loads(await FirecrawlBackend([]).search("q"))
        headers = post.call_args.kwargs["headers"]
    assert "Authorization" not in headers
    assert out["results"] == []


async def test_firecrawl_http_error_returns_error_json():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(status_code=402)
        out = json.loads(await FirecrawlBackend([]).search("q"))
    assert "error" in out


async def test_firecrawl_recency_maps_to_tbs():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(json_data={"success": True, "data": {}})
        await FirecrawlBackend([]).search("q", time_range="year")
        body = post.call_args.kwargs["json"]
    assert body["tbs"] == "qdr:y"


# --- kagi -------------------------------------------------------------------


async def test_kagi_maps_data_search_rows():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(
            json_data={
                "data": {
                    "search": [
                        {"title": "K1", "url": "https://k/1", "snippet": "s1"},
                        {"title": "K2", "url": "https://k/2", "description": "s2"},
                        {"title": "no url"},
                    ]
                }
            }
        )
        out = json.loads(await KagiBackend(["kag-k"]).search("q", max_results=5))
        headers = post.call_args.kwargs["headers"]
        body = post.call_args.kwargs["json"]
    assert headers["Authorization"] == "Bearer kag-k"
    assert body == {"query": "q", "limit": 5}
    assert [r["url"] for r in out["results"]] == ["https://k/1", "https://k/2"]
    assert out["results"][1]["snippet"] == "s2"


async def test_kagi_http_error_returns_error_json():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(status_code=401)
        out = json.loads(await KagiBackend(["bad"]).search("q"))
    assert "error" in out


# --- factory + uvx runnability + chain --------------------------------------


def test_factory_builds_keyless_backends_without_keys(monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert isinstance(_make_backend("duckduckgo"), DuckDuckGoBackend)
    assert isinstance(_make_backend("startpage"), StartpageBackend)
    fc = _make_backend("firecrawl")
    assert isinstance(fc, FirecrawlBackend)
    assert fc.keys == []


def test_factory_kagi_requires_key(monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    try:
        _make_backend("kagi")
    except ValueError as exc:
        assert "KAGI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing KAGI_API_KEY")


def test_chain_names_include_new_backends(monkeypatch):
    monkeypatch.setenv(
        "SEARCH_BACKENDS", "tavily, kagi, firecrawl, duckduckgo, startpage"
    )
    assert chain_backend_names() == [
        "tavily",
        "kagi",
        "firecrawl",
        "duckduckgo",
        "startpage",
    ]


def test_uvx_runnable_with_credential_free_chain(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "duckduckgo,startpage")
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert has_uvx_runnable_backend() is True


def test_uvx_not_runnable_with_only_keyless_kagi(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "kagi")
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    assert has_uvx_runnable_backend() is False


async def test_chain_falls_through_bot_challenge_to_credential_free(monkeypatch):
    # tavily (missing key) is skipped; duckduckgo is bot-challenged; startpage
    # answers — the credential-free tail keeps the chain usable with zero keys.
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily,duckduckgo,startpage")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    async def fake_get(self, url, **kwargs):
        assert urlsplit(url).hostname == "www.startpage.com"
        return _resp(text=STARTPAGE_PAGE)

    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        post.return_value = _resp(text=DDG_ANOMALY_PAGE)
        with unittest.mock.patch("httpx.AsyncClient.get", new=fake_get):
            out = json.loads(await run_search_chain("q"))
    assert out["results"][0]["source"] == "startpage"


def test_chain_skips_unbuildable_keeps_new_backends(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "kagi,duckduckgo")
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    backends = search_backends_from_env()
    assert len(backends) == 1
    assert isinstance(backends[0], DuckDuckGoBackend)
