"""Tests for search strategies: query expansion, find similar, snippet enrichment."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from wet_mcp.sources.search_strategies import (
    _extract_passage,
    enrich_snippets,
    expand_query,
    find_similar,
    generate_hyde_query,
)


def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock LLM response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# expand_query
# ---------------------------------------------------------------------------


async def test_expand_query_success():
    """LLM returns 2 alternative queries -- happy path."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response("python web scraping\nweb crawling python"),
        ),
    ):

        result = await expand_query("python scraping")

        assert len(result) == 3
        assert result[0] == "python scraping"
        assert result[1] == "python web scraping"
        assert result[2] == "web crawling python"


async def test_expand_query_local_mode_fallback():
    """Local mode (no LLM) returns only original query."""
    with patch("wet_mcp.sources.search_strategies.has_llm_provider", return_value=False):

        result = await expand_query("python scraping")

        assert result == ["python scraping"]


async def test_expand_query_llm_failure_fallback():
    """LLM call fails -- gracefully returns original query."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ),
    ):

        result = await expand_query("python scraping")

        assert result == ["python scraping"]


async def test_expand_query_numbered_lines():
    """LLM returns numbered lines -- numbers are stripped."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response("1. alternative one\n2) alternative two"),
        ),
    ):

        result = await expand_query("original")

        assert result[0] == "original"
        assert result[1] == "alternative one"
        assert result[2] == "alternative two"


async def test_expand_query_empty_llm_response():
    """LLM returns empty content -- falls back to original."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response(""),
        ),
    ):

        result = await expand_query("original")

        # Empty response -> no alt queries parsed, just original
        assert result == ["original"]


async def test_expand_query_more_than_two_alts():
    """LLM returns more than 2 alternatives -- only first 2 kept."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response("alt1\nalt2\nalt3\nalt4"),
        ),
    ):

        result = await expand_query("original")

        assert len(result) == 3
        assert result[0] == "original"


# ---------------------------------------------------------------------------
# find_similar
# ---------------------------------------------------------------------------

SAMPLE_PAGES = [
    {
        "url": "https://example.com/page",
        "title": "Example Page",
        "content": "This is about Python web scraping with beautiful soup.",
    }
]

SEARCH_RESULTS = json.dumps(
    {
        "results": [
            {
                "url": "https://other.com/similar",
                "title": "Similar Page",
                "snippet": "Also about scraping",
                "source": "google",
            }
        ],
        "total": 1,
        "query": "keywords -site:example.com",
    }
)


async def test_find_similar_success():
    """Happy path: extract content, get keywords, search."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.raw_extract",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_PAGES),
        ),
        patch(
            "wet_mcp.sources.search_strategies._extract_keywords",
            new_callable=AsyncMock,
            return_value="python web scraping beautifulsoup",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=SEARCH_RESULTS,
        ) as mock_search,
    ):
        result = await find_similar(
            url="https://example.com/page",
            searxng_url="http://localhost:8080",
        )

        parsed = json.loads(result)
        assert parsed["total"] == 1
        assert parsed["results"][0]["url"] == "https://other.com/similar"
        mock_search.assert_awaited_once_with(
            searxng_url="http://localhost:8080",
            query="python web scraping beautifulsoup -site:example.com",
            max_results=10,
        )


async def test_find_similar_extract_failure():
    """Extract fails -- returns error JSON."""
    error_pages = [{"url": "https://bad.com", "error": "Failed to load"}]
    with patch(
        "wet_mcp.sources.search_strategies.raw_extract",
        new_callable=AsyncMock,
        return_value=json.dumps(error_pages),
    ):
        result = await find_similar(url="https://bad.com")

        parsed = json.loads(result)
        assert "error" in parsed
        assert "Could not extract" in parsed["error"]


async def test_find_similar_empty_pages():
    """Extract returns empty list -- returns error JSON."""
    with patch(
        "wet_mcp.sources.search_strategies.raw_extract",
        new_callable=AsyncMock,
        return_value=json.dumps([]),
    ):
        result = await find_similar(url="https://empty.com")

        parsed = json.loads(result)
        assert "error" in parsed


async def test_find_similar_auto_searxng_url(monkeypatch):
    """A local single-user SearXNG chain is started before similar search."""
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.setattr("wet_mcp.runtime.current_sub", lambda: "default")
    monkeypatch.setattr(
        "wet_mcp.sources.search_backends.chain_backend_names",
        lambda: ["searxng"],
    )
    with (
        patch(
            "wet_mcp.sources.search_strategies.raw_extract",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_PAGES),
        ),
        patch(
            "wet_mcp.sources.search_strategies._extract_keywords",
            new_callable=AsyncMock,
            return_value="keywords",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=SEARCH_RESULTS,
        ) as mock_search,
        patch(
            "wet_mcp.searxng_runner.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://localhost:41592",
        ) as mock_ensure,
    ):
        result = await find_similar(url="https://example.com/page")

        parsed = json.loads(result)
        assert "results" in parsed
        mock_ensure.assert_awaited_once_with()
        mock_search.assert_awaited_once_with(
            searxng_url="http://localhost:41592",
            query="keywords -site:example.com",
            max_results=10,
        )


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------


async def test_extract_keywords_local_mode():
    """Local mode returns title as keywords."""
    from wet_mcp.sources.search_strategies import _extract_keywords

    with patch("wet_mcp.sources.search_strategies.has_llm_provider", return_value=False):

        result = await _extract_keywords("some content", "My Title")
        assert result == "My Title"


async def test_extract_keywords_local_no_title():
    """Local mode with no title returns content prefix."""
    from wet_mcp.sources.search_strategies import _extract_keywords

    with patch("wet_mcp.sources.search_strategies.has_llm_provider", return_value=False):

        result = await _extract_keywords("some content here", "")
        assert result == "some content here"


async def test_extract_keywords_llm_success():
    """LLM returns comma-separated keywords."""
    from wet_mcp.sources.search_strategies import _extract_keywords

    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response("python, scraping, web, automation"),
        ),
    ):

        result = await _extract_keywords("content about python", "Python Guide")
        assert result == "python, scraping, web, automation"


async def test_extract_keywords_llm_failure():
    """LLM fails -- falls back to title."""
    from wet_mcp.sources.search_strategies import _extract_keywords

    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ),
    ):

        result = await _extract_keywords("content", "Fallback Title")
        assert result == "Fallback Title"


# ---------------------------------------------------------------------------
# enrich_snippets
# ---------------------------------------------------------------------------

ENRICHMENT_PAGES = [
    {
        "url": "https://a.com",
        "title": "Page A",
        "content": "This page discusses python web scraping techniques and best practices for data extraction.",
    },
    {
        "url": "https://b.com",
        "title": "Page B",
        "content": "Another page about python programming.",
    },
]


async def test_enrich_snippets_success():
    """Top results get enriched snippets from actual content."""
    input_results = [
        {"url": "https://a.com", "title": "A", "snippet": "old snippet"},
        {"url": "https://b.com", "title": "B", "snippet": "old snippet"},
    ]

    with patch(
        "wet_mcp.sources.search_strategies.raw_extract",
        new_callable=AsyncMock,
        return_value=json.dumps(ENRICHMENT_PAGES),
    ):
        result = await enrich_snippets(input_results, query="python scraping", top_n=5)

        assert len(result) == 2
        # First result should be enriched (content contains query terms)
        assert result[0].get("enriched") is True
        assert result[0]["snippet"] != "old snippet"


async def test_enrich_snippets_empty_results():
    """Empty results list returns empty list."""
    result = await enrich_snippets([], query="anything")
    assert result == []


async def test_enrich_snippets_extract_failure():
    """Extract failure -- returns original results unchanged."""
    input_results = [
        {"url": "https://a.com", "title": "A", "snippet": "original"},
    ]

    with patch(
        "wet_mcp.sources.search_strategies.raw_extract",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        result = await enrich_snippets(input_results, query="test", top_n=5)

        assert len(result) == 1
        assert result[0]["snippet"] == "original"
        assert "enriched" not in result[0]


async def test_enrich_snippets_no_urls():
    """Results without URLs are returned as-is."""
    input_results = [
        {"title": "No URL", "snippet": "something"},
    ]

    result = await enrich_snippets(input_results, query="test")
    assert result == input_results


async def test_enrich_snippets_preserves_rest():
    """Results beyond top_n are preserved unchanged."""
    input_results = [
        {"url": "https://a.com", "title": "A", "snippet": "top"},
        {"url": "https://b.com", "title": "B", "snippet": "rest"},
    ]

    with patch(
        "wet_mcp.sources.search_strategies.raw_extract",
        new_callable=AsyncMock,
        return_value=json.dumps(ENRICHMENT_PAGES),
    ):
        result = await enrich_snippets(input_results, query="python", top_n=1)

        assert len(result) == 2
        # Second result (beyond top_n=1) should be unchanged
        assert result[1]["snippet"] == "rest"
        assert "enriched" not in result[1]


# ---------------------------------------------------------------------------
# _extract_passage
# ---------------------------------------------------------------------------


def test_extract_passage_finds_best_window():
    """Passage extraction finds window with most query terms."""
    content = (
        "Introduction to the topic. " * 20
        + "Python web scraping is essential for data extraction. "
        + "More filler content. " * 20
    )
    result = _extract_passage(content, ["python", "scraping", "data"], max_chars=200)

    assert "python" in result.lower() or "scraping" in result.lower()


def test_extract_passage_no_match_returns_beginning():
    """No query terms found -- returns content beginning."""
    content = "This content has nothing to do with the query terms."
    result = _extract_passage(content, ["xyz", "abc"], max_chars=100)

    assert result == content.strip()


def test_extract_passage_short_content():
    """Content shorter than max_chars is handled correctly."""
    content = "Short content."
    result = _extract_passage(content, ["short"], max_chars=500)

    assert "Short content" in result


def test_extract_passage_empty_query_terms():
    """Empty query terms -- returns beginning of content."""
    content = "Some content here for testing."
    result = _extract_passage(content, [], max_chars=100)

    assert result == content.strip()


def test_extract_passage_mid_content_cleans_start():
    """Passage starting mid-content trims partial first word."""
    # Create content where best match is not at the start
    content = "a " * 200 + "python scraping data " + "b " * 200
    result = _extract_passage(content, ["python", "scraping", "data"], max_chars=100)

    # Should not start with a partial word
    assert not result[0].isspace() if result else True


# ---------------------------------------------------------------------------
# generate_hyde_query
# ---------------------------------------------------------------------------


async def test_generate_hyde_query_success():
    """LLM returns hypothetical document text -- happy path."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response(
                "The requests library provides a simple HTTP client for Python. "
                "Use requests.get(url) to make GET requests."
            ),
        ),
    ):

        result = await generate_hyde_query("how to make HTTP requests", "requests")

        assert result is not None
        assert "requests" in result.lower()


async def test_generate_hyde_query_local_mode():
    """Local mode (no LLM) returns None."""
    with patch("wet_mcp.sources.search_strategies.has_llm_provider", return_value=False):

        result = await generate_hyde_query("some query", "some-lib")

        assert result is None


async def test_generate_hyde_query_llm_failure():
    """LLM call fails -- returns None gracefully."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ),
    ):

        result = await generate_hyde_query("some query", "some-lib")

        assert result is None


async def test_generate_hyde_query_empty_response():
    """LLM returns empty content -- returns None."""
    with (
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=True,
        ),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-4", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            new_callable=AsyncMock,
            return_value=_mock_llm_response(""),
        ),
    ):

        result = await generate_hyde_query("some query", "some-lib")

        assert result is None
