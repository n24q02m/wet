import json
import unittest.mock

import pytest

from wet_mcp.config import settings
from wet_mcp.sources import rerank as rerank_mod
from wet_mcp.sources import search_backends
from wet_mcp.sources.rerank import CohereReranker, maybe_rerank, reranker_from_env
from wet_mcp.sources.search_backends import OpenRouterBackend, _make_backend


async def test_openrouter_maps_url_citation_annotations():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "annotations": [
                                {
                                    "url_citation": {
                                        "url": "https://e/1",
                                        "title": "R1",
                                        "content": "c1",
                                    }
                                },
                                {
                                    "url_citation": {
                                        "url": "https://e/1",
                                        "title": "dup",
                                        "content": "dup",
                                    }
                                },
                                {"file_citation": {"file_id": "f1"}},
                                {
                                    "url_citation": {
                                        "url": "https://e/2",
                                        "title": "R2",
                                    }
                                },
                            ]
                        }
                    }
                ]
            }
        )
        post.return_value = resp
        out = json.loads(
            await OpenRouterBackend(
                ["k"], model="m", base_url="https://openrouter.ai/api/v1"
            ).search("q", max_results=5)
        )
    assert out["total"] == 2
    assert out["query"] == "q"
    assert [r["url"] for r in out["results"]] == ["https://e/1", "https://e/2"]
    assert out["results"][0]["source"] == "openrouter"
    assert out["results"][0]["snippet"] == "c1"
    assert "snippet" in out["results"][1]
    body = post.call_args.kwargs["json"]
    assert body["model"] == "m"
    assert body["tools"][0]["type"] == "openrouter:web_search"
    assert body["tools"][0]["parameters"]["max_results"] == 5


async def test_openrouter_http_error_returns_error_json():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 402
        post.return_value = resp
        out = json.loads(
            await OpenRouterBackend(
                ["k"], model="m", base_url="https://openrouter.ai/api/v1"
            ).search("q")
        )
    assert "error" in out


def test_factory_openrouter_requires_key(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _make_backend("openrouter")


def test_factory_openrouter_builds_from_settings(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "k1,k2")
    backend = _make_backend("openrouter")
    assert isinstance(backend, OpenRouterBackend)
    assert backend.keys == ["k1", "k2"]
    assert backend.model == settings.openrouter_model


async def test_maybe_rerank_reorders_and_tags():
    data = {
        "results": [{"url": "https://a"}, {"url": "https://b"}],
        "total": 2,
        "query": "q",
    }
    reranker = unittest.mock.AsyncMock()
    reranker.rerank.return_value = [data["results"][1], data["results"][0]]
    with unittest.mock.patch.object(
        rerank_mod, "reranker_from_env", return_value=reranker
    ):
        out = await maybe_rerank("q", data, 5)
    assert [r["url"] for r in out["results"]] == ["https://b", "https://a"]
    assert out["reranked_by"] == "cohere"
    assert out["total"] == 2


async def test_maybe_rerank_disabled_keeps_envelope():
    data = {
        "results": [{"url": "https://a"}, {"url": "https://b"}],
        "total": 2,
        "query": "q",
    }
    out = await maybe_rerank("q", data, 5)
    assert out is data
    assert "reranked_by" not in out


async def test_maybe_rerank_failure_keeps_original_order():
    data = {
        "results": [{"url": "https://a"}, {"url": "https://b"}],
        "total": 2,
        "query": "q",
    }
    reranker = unittest.mock.AsyncMock()
    reranker.rerank.side_effect = RuntimeError("HTTP 500")
    with unittest.mock.patch.object(
        rerank_mod, "reranker_from_env", return_value=reranker
    ):
        out = await maybe_rerank("q", data, 5)
    assert out["results"][0]["url"] == "https://a"
    assert "reranked_by" not in out


async def test_maybe_rerank_skips_error_envelope_and_singletons():
    error_data = {"error": "chain exhausted", "results": []}
    assert await maybe_rerank("q", dict(error_data), 5) == error_data
    single = {"results": [{"url": "https://a"}], "total": 1}
    assert await maybe_rerank("q", dict(single), 5) == single


def test_reranker_from_env_requires_optin_and_key(monkeypatch):
    monkeypatch.setattr(settings, "wet_search_rerank", False)
    monkeypatch.setattr(settings, "cohere_api_key", "k")
    assert reranker_from_env() is None
    monkeypatch.setattr(settings, "wet_search_rerank", True)
    monkeypatch.setattr(settings, "cohere_api_key", "")
    assert reranker_from_env() is None
    monkeypatch.setattr(settings, "cohere_api_key", "k")
    r = reranker_from_env()
    assert r is not None
    assert r.model == settings.cohere_rerank_model
    assert r.base_url == settings.cohere_base_url


async def test_cohere_reranker_maps_scores_onto_inputs():
    with unittest.mock.patch("httpx.AsyncClient.post") as post:
        resp = unittest.mock.AsyncMock()
        resp.status_code = 200
        resp.json = unittest.mock.Mock(
            return_value={
                "results": [
                    {"index": 1, "relevance_score": 0.987},
                    {"index": 0, "relevance_score": 0.123},
                ]
            }
        )
        post.return_value = resp
        r = CohereReranker(
            "k", model="rerank-v4.0-fast", base_url="https://api.cohere.com"
        )
        out = await r.rerank(
            "q",
            [
                {"url": "https://a", "title": "A", "snippet": "s"},
                {"url": "https://b", "title": "B", "snippet": "t"},
            ],
            top_n=2,
        )
    assert [item["url"] for item in out] == ["https://b", "https://a"]
    assert out[0]["rerank_score"] == 0.987
    assert out[0]["title"] == "B"
    body = post.call_args.kwargs["json"]
    assert body["model"] == "rerank-v4.0-fast"
    assert body["top_n"] == 2
    assert len(body["documents"]) == 2


async def test_run_search_chain_applies_cohere_rerank(monkeypatch):
    payload = json.dumps(
        {
            "results": [
                {
                    "url": "https://a",
                    "title": "A",
                    "snippet": "s",
                    "source": "duckduckgo",
                },
                {
                    "url": "https://b",
                    "title": "B",
                    "snippet": "t",
                    "source": "duckduckgo",
                },
            ],
            "total": 2,
            "query": "q",
        }
    )
    fake_backend = unittest.mock.AsyncMock()
    fake_backend.name = "duckduckgo"
    fake_backend.search.return_value = payload
    monkeypatch.setattr(
        search_backends, "search_backends_from_env", lambda *a, **k: [fake_backend]
    )
    monkeypatch.setattr(settings, "wet_search_rerank", True)
    reranker = unittest.mock.AsyncMock()
    reranker.rerank.return_value = [{"url": "https://b"}, {"url": "https://a"}]
    with unittest.mock.patch.object(
        rerank_mod, "reranker_from_env", return_value=reranker
    ):
        out = json.loads(await search_backends.run_search_chain("q"))
    assert out["reranked_by"] == "cohere"
    assert out["results"][0]["url"] == "https://b"
    assert out["search_backend"]["selected"] == "duckduckgo"
