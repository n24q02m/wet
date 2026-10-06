import json
import unittest.mock

import pytest

from wet.config import settings
from wet.sources.search_backends import OpenRouterBackend, _make_backend


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
    monkeypatch.setattr(settings, "openrouter_model", "test/model")
    backend = _make_backend("openrouter")
    assert isinstance(backend, OpenRouterBackend)
    assert backend.keys == ["k1", "k2"]
    assert backend.model == "test/model"


def test_factory_openrouter_requires_model(monkeypatch):
    # No sanctioned default: with a key but no model the factory must fail
    # closed instead of silently routing spend to a hardcoded slug.
    monkeypatch.setenv("SEARCH_BACKEND", "openrouter")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "k1,k2")
    monkeypatch.setattr(settings, "openrouter_model", "")
    with pytest.raises(ValueError, match="OPENROUTER_MODEL"):
        _make_backend("openrouter")
