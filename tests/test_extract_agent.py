"""Tests for ``extract(action="agent")`` orchestration (Phase 3 Task 2)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources import agent_orchestrator as ao


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Default to NO LLM provider key set; per-test sets what they need."""
    for key in ao._PROVIDER_KEYS + ("ANTHROPIC_API_KEY",):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def _gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def _make_search_payload(urls: list[str]) -> str:
    return json.dumps(
        {
            "results": [
                {
                    "url": u,
                    "title": f"Title for {u}",
                    "snippet": f"Snippet for {u}",
                    "source": "searxng",
                }
                for u in urls
            ]
        }
    )


@pytest.mark.asyncio
async def test_agent_uses_later_search_backend_and_keeps_provenance(
    _gemini_env,
) -> None:
    first = MagicMock(name="searxng")
    first.name = "searxng"
    first.search = AsyncMock(
        return_value=json.dumps({"results": [], "total": 0, "query": "q"})
    )
    second = MagicMock(name="brave")
    second.name = "brave"
    second.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/hit",
                        "title": "Selected title",
                        "snippet": "Selected snippet",
                        "source": "brave",
                    }
                ],
                "total": 1,
                "query": "q",
            }
        )
    )
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first, second],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new=AsyncMock(
                return_value=_make_extract_payload("https://example.com/hit")
            ),
        ),
        patch.object(ao, "_llm_synthesize", new=AsyncMock(return_value="answer [1]")),
    ):
        result = await ao.run_agent("q", max_urls=1)

    assert isinstance(result, dict)
    assert result["sources"] == [
        {
            "index": 1,
            "url": "https://example.com/hit",
            "title": "Title for https://example.com/hit",
            "search_provider": "brave",
        }
    ]
    assert result["per_url_metadata"][0]["search_provider"] == "brave"


@pytest.mark.asyncio
async def test_agent_uses_later_search_backend_after_error(_gemini_env) -> None:
    first = MagicMock(name="searxng")
    first.name = "searxng"
    first.search = AsyncMock(side_effect=RuntimeError("first backend down"))
    second = MagicMock(name="brave")
    second.name = "brave"
    second.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/hit",
                        "title": "Selected title",
                        "snippet": "Selected snippet",
                        "source": "brave",
                    }
                ],
                "total": 1,
                "query": "q",
            }
        )
    )
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first, second],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new=AsyncMock(
                return_value=_make_extract_payload("https://example.com/hit")
            ),
        ),
        patch.object(ao, "_llm_synthesize", new=AsyncMock(return_value="answer [1]")),
    ):
        result = await ao.run_agent("q", max_urls=1)

    assert isinstance(result, dict)
    assert result["sources"][0]["search_provider"] == "brave"
    assert result["per_url_metadata"][0]["search_provider"] == "brave"


@pytest.mark.asyncio
async def test_agent_all_empty_search_keeps_no_results_contract(_gemini_env):
    first = MagicMock(name="searxng")
    first.name = "searxng"
    first.search = AsyncMock(
        return_value=json.dumps({"results": [], "total": 0, "query": "q"})
    )
    second = MagicMock(name="brave")
    second.name = "brave"
    second.search = AsyncMock(
        return_value=json.dumps({"results": [], "total": 0, "query": "q"})
    )
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first, second],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
    ):
        result = await ao.run_agent("q")

    assert isinstance(result, dict)
    assert result["sources"] == []
    assert result["per_url_metadata"] == []
    assert "No results found" in result["markdown"]


@pytest.mark.asyncio
async def test_agent_all_failed_search_is_hard_failure(_gemini_env):
    first = MagicMock(name="searxng")
    first.name = "searxng"
    first.search = AsyncMock(side_effect=RuntimeError("first backend down"))
    second = MagicMock(name="brave")
    second.name = "brave"
    second.search = AsyncMock(side_effect=RuntimeError("second backend down"))
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first, second],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
    ):
        result = await ao.run_agent("q")

    assert result == (
        "Error: search failed: Search backend chain exhausted after provider failure"
    )


@pytest.mark.asyncio
async def test_agent_uses_later_search_backend_after_malformed_results(_gemini_env):
    first = MagicMock(name="searxng")
    first.name = "searxng"
    first.search = AsyncMock(
        return_value=json.dumps({"results": "not-a-list", "total": 1, "query": "q"})
    )
    second = MagicMock(name="brave")
    second.name = "brave"
    second.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/hit",
                        "title": "Selected title",
                        "snippet": "Selected snippet",
                        "source": "brave",
                    }
                ],
                "total": 1,
                "query": "q",
            }
        )
    )
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first, second],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new=AsyncMock(
                return_value=_make_extract_payload("https://example.com/hit")
            ),
        ),
        patch.object(ao, "_llm_synthesize", new=AsyncMock(return_value="answer [1]")),
    ):
        result = await ao.run_agent("q", max_urls=1)

    assert isinstance(result, dict)
    assert result["sources"][0]["search_provider"] == "brave"
    assert result["per_url_metadata"][0]["search_provider"] == "brave"


@pytest.mark.asyncio
async def test_agent_preserves_multi_result_order_and_search_title_fallback(
    _gemini_env,
):
    first_url = "https://example.com/first"
    second_url = "https://example.com/second"
    first = MagicMock(name="brave")
    first.name = "brave"
    first.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {
                        "url": first_url,
                        "title": "Search title one",
                        "snippet": "Search snippet one",
                        "source": "brave",
                    },
                    {
                        "url": second_url,
                        "title": "Search title two",
                        "snippet": "Search snippet two",
                        "source": "exa",
                    },
                ],
                "total": 2,
                "query": "q",
            }
        )
    )
    with (
        patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[first],
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(side_effect=AssertionError("direct SearXNG call")),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new=AsyncMock(
                side_effect=[
                    _make_extract_payload(first_url, "First body"),
                    json.dumps(
                        [
                            {
                                "url": second_url,
                                "markdown": "Second body",
                                "metadata": {"scrape_strategy_used": "basic_http"},
                            }
                        ]
                    ),
                ]
            ),
        ),
        patch.object(
            ao, "_llm_synthesize", new=AsyncMock(return_value="answer [1] [2]")
        ),
    ):
        result = await ao.run_agent("q", max_urls=2)

    assert isinstance(result, dict)
    assert result["sources"] == [
        {
            "index": 1,
            "url": first_url,
            "title": f"Title for {first_url}",
            "search_provider": "brave",
        },
        {
            "index": 2,
            "url": second_url,
            "title": "Search title two",
            "search_provider": "exa",
        },
    ]
    assert [
        (row["url"], row["search_provider"]) for row in result["per_url_metadata"]
    ] == [(first_url, "brave"), (second_url, "exa")]


@pytest.mark.asyncio
async def test_agent_search_error_envelope_is_hard_failure(_gemini_env) -> None:
    error_payload = json.dumps({"results": [], "error": "unavailable"})
    with (
        patch.object(
            ao,
            "run_search_chain",
            new=AsyncMock(return_value=error_payload),
            create=True,
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(return_value=error_payload),
        ),
    ):
        result = await ao.run_agent("q")
    assert result == "Error: search failed: unavailable"


@pytest.mark.asyncio
async def test_agent_invalid_search_payload_is_hard_failure(_gemini_env) -> None:
    with (
        patch.object(
            ao,
            "run_search_chain",
            new=AsyncMock(return_value="not json"),
            create=True,
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(return_value="not json"),
        ),
    ):
        result = await ao.run_agent("q")
    assert result == "Error: search failed: JSONDecodeError"


@pytest.mark.asyncio
async def test_agent_legitimate_empty_search_keeps_no_results_contract(_gemini_env):
    empty_payload = json.dumps({"results": [], "total": 0, "query": "q"})
    with (
        patch.object(
            ao,
            "run_search_chain",
            new=AsyncMock(return_value=empty_payload),
            create=True,
        ),
        patch(
            "wet_mcp.sources.searxng.search",
            new=AsyncMock(return_value=empty_payload),
        ),
    ):
        result = await ao.run_agent("q")
    assert isinstance(result, dict)
    assert result["sources"] == []
    assert result["per_url_metadata"] == []
    assert "No results found" in result["markdown"]


def _make_extract_payload(url: str, body: str = "Body content") -> str:
    return json.dumps(
        [
            {
                "url": url,
                "markdown": body,
                "clean_text": body,
                "metadata": {
                    "title": f"Title for {url}",
                    "scrape_strategy_used": "basic_http",
                },
            }
        ]
    )


@pytest.mark.asyncio
async def test_no_provider_returns_structured_error() -> None:
    result = await ao.run_agent(query="anything")
    assert isinstance(result, str)
    assert result.startswith("Error: no LLM provider detected")
    assert "GEMINI_API_KEY" in result


@pytest.mark.asyncio
async def test_empty_query_returns_error(_gemini_env) -> None:
    result = await ao.run_agent(query="   ")
    assert isinstance(result, str)
    assert result.startswith("Error: query is required")


@pytest.mark.asyncio
async def test_pipeline_search_then_extract_then_synthesize(_gemini_env) -> None:
    urls = [f"https://example.com/{i}" for i in range(5)]
    with (
        patch.object(
            ao,
            "run_search_chain",
            new_callable=AsyncMock,
            return_value=_make_search_payload(urls),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new_callable=AsyncMock,
            side_effect=lambda urls=(), **_kw: _make_extract_payload(
                (urls or ["https://x"])[0]
            ),
        ),
        patch(
            "wet_mcp.sources.agent_orchestrator._llm_synthesize",
            new_callable=AsyncMock,
            return_value="# Synthesis\n\nFact [1] another [2]. ## Sources\n- [1]\n- [2]",
        ),
    ):
        result = await ao.run_agent(query="explain X", max_urls=5)

    assert isinstance(result, dict)
    assert "markdown" in result
    assert "Synthesis" in result["markdown"]
    assert len(result["sources"]) == 5
    assert result["sources"][0]["index"] == 1
    assert result["sources"][0]["url"] == "https://example.com/0"
    assert len(result["per_url_metadata"]) == 5
    assert result["per_url_metadata"][0]["extract_strategy"] == "basic_http"


@pytest.mark.asyncio
async def test_token_budget_caps_per_extract_size(_gemini_env) -> None:
    huge = "x" * 50000
    extracts = [
        {"url": f"https://e.com/{i}", "markdown": huge, "metadata": {"title": "T"}}
        for i in range(5)
    ]
    prompt = ao.build_cited_prompt("q", extracts, token_budget=10000)
    # token_budget=10000 -> per-extract chars ~ ((10000-200)//5) * 4 = 7840
    assert len(prompt) < 5 * 50000, "per-extract truncation must apply"
    assert "[truncated for token budget]" in prompt


@pytest.mark.asyncio
async def test_max_urls_default_5_cap_20(_gemini_env) -> None:
    # Default
    assert ao._clamp_max_urls(0) == 1
    assert ao._clamp_max_urls(5) == 5
    assert ao._clamp_max_urls(100) == 20
    assert ao._clamp_max_urls(20) == 20


@pytest.mark.asyncio
async def test_synthesis_prompt_includes_numbered_citations(_gemini_env) -> None:
    extracts = [
        {"url": "https://a.com", "markdown": "Alpha", "metadata": {"title": "A"}},
        {"url": "https://b.com", "markdown": "Beta", "metadata": {"title": "B"}},
        {"url": "https://c.com", "markdown": "Gamma", "metadata": {"title": "C"}},
    ]
    prompt = ao.build_cited_prompt("compare", extracts, token_budget=10000)
    assert "[1]" in prompt
    assert "[2]" in prompt
    assert "[3]" in prompt
    assert "https://a.com" in prompt
    assert "Alpha" in prompt
    assert "preserve numeric citation markers" in prompt.lower()


@pytest.mark.asyncio
async def test_search_failure_returns_error_string(_gemini_env) -> None:
    with patch.object(
        ao,
        "run_search_chain",
        new_callable=AsyncMock,
        return_value=json.dumps({"results": [], "error": "unavailable"}),
    ):
        result = await ao.run_agent(query="x")
    assert isinstance(result, str)
    assert "Error: search failed" in result


@pytest.mark.asyncio
async def test_no_search_results_returns_empty_synthesis(_gemini_env) -> None:
    with patch.object(
        ao,
        "run_search_chain",
        new_callable=AsyncMock,
        return_value=json.dumps({"results": []}),
    ):
        result = await ao.run_agent(query="obscure")
    assert isinstance(result, dict)
    assert result["sources"] == []
    assert "No results found" in result["markdown"]


@pytest.mark.asyncio
async def test_synthesis_failure_returns_error_string(_gemini_env) -> None:
    urls = ["https://example.com/1"]
    with (
        patch.object(
            ao,
            "run_search_chain",
            new_callable=AsyncMock,
            return_value=_make_search_payload(urls),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new_callable=AsyncMock,
            return_value=_make_extract_payload(urls[0]),
        ),
        patch(
            "wet_mcp.sources.agent_orchestrator._llm_synthesize",
            new_callable=AsyncMock,
            side_effect=RuntimeError("api 500"),
        ),
    ):
        result = await ao.run_agent(query="test")
    assert isinstance(result, str)
    assert "Error: synthesis failed" in result


@pytest.mark.asyncio
async def test_extract_error_propagates_to_per_url_metadata(_gemini_env) -> None:
    urls = ["https://broken.com/1"]
    with (
        patch.object(
            ao,
            "run_search_chain",
            new_callable=AsyncMock,
            return_value=_make_search_payload(urls),
        ),
        patch(
            "wet_mcp.sources.crawler.extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "wet_mcp.sources.agent_orchestrator._llm_synthesize",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        result = await ao.run_agent(query="test")
    assert isinstance(result, dict)
    assert result["per_url_metadata"][0]["error"] == "boom"


@pytest.mark.asyncio
async def test_provider_detection_priority(_gemini_env, monkeypatch) -> None:
    # Gemini wins when set
    assert ao.detect_llm_provider() == "GEMINI_API_KEY"
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert ao.detect_llm_provider() == "OPENAI_API_KEY"
    monkeypatch.setenv("XAI_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert ao.detect_llm_provider() == "XAI_API_KEY"
    monkeypatch.delenv("XAI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    assert ao.detect_llm_provider() == "GOOGLE_API_KEY"
