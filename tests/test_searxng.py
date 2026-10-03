"""Tests for SearXNG search wrapper (delegates to web-core).

Tests the wet wrapper layer:
- URL normalization (re-exported from web-core)
- Per-domain result cap (re-exported from web-core)
- Query filtering (re-exported from web-core)
- JSON conversion + health check wrapper
"""

import json
import unittest.mock

import pytest

from wet.sources.searxng import (
    _apply_domain_cap,
    _build_filtered_query,
    _normalize_url,
    search,
)

# --- _normalize_url tests (web-core's normalize_url) ---


class TestNormalizeUrl:
    def test_strip_www_prefix(self):
        assert (
            _normalize_url("https://www.example.com/page") == "https://example.com/page"
        )

    def test_no_www_unchanged(self):
        assert _normalize_url("https://example.com/page") == "https://example.com/page"

    def test_strip_trailing_slash(self):
        assert _normalize_url("https://example.com/") == "https://example.com"

    def test_strip_trailing_slash_with_path(self):
        assert _normalize_url("https://example.com/page/") == "https://example.com/page"

    def test_remove_utm_source(self):
        result = _normalize_url("https://example.com/page?utm_source=google&key=val")
        assert "utm_source" not in result
        assert "key=val" in result

    def test_remove_utm_medium(self):
        result = _normalize_url("https://example.com?utm_medium=cpc")
        assert "utm_medium" not in result

    def test_remove_utm_campaign(self):
        result = _normalize_url("https://example.com?utm_campaign=spring")
        assert "utm_campaign" not in result

    def test_remove_utm_term(self):
        result = _normalize_url("https://example.com?utm_term=shoes")
        assert "utm_term" not in result

    def test_remove_utm_content(self):
        result = _normalize_url("https://example.com?utm_content=banner")
        assert "utm_content" not in result

    def test_remove_fbclid(self):
        result = _normalize_url("https://example.com?fbclid=abc123")
        assert "fbclid" not in result

    def test_remove_gclid(self):
        result = _normalize_url("https://example.com?gclid=xyz")
        assert "gclid" not in result

    def test_remove_msclkid(self):
        result = _normalize_url("https://example.com?msclkid=abc")
        assert "msclkid" not in result

    def test_remove_yclid(self):
        result = _normalize_url("https://example.com?yclid=abc")
        assert "yclid" not in result

    def test_remove_ref(self):
        result = _normalize_url("https://example.com?ref=twitter")
        assert "ref" not in result

    def test_remove_mc_params(self):
        result = _normalize_url("https://example.com?mc_cid=abc&mc_eid=def")
        assert "mc_cid" not in result
        assert "mc_eid" not in result

    def test_remove_multiple_tracking_params(self):
        url = "https://example.com/page?utm_source=google&utm_medium=cpc&fbclid=abc&real=value"
        result = _normalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "fbclid" not in result
        assert "real=value" in result

    def test_preserve_meaningful_params(self):
        url = "https://example.com/search?q=python&page=2&lang=en"
        result = _normalize_url(url)
        assert "q=python" in result
        assert "page=2" in result
        assert "lang=en" in result

    def test_all_params_removed_no_question_mark(self):
        result = _normalize_url("https://example.com/page?utm_source=google")
        assert result == "https://example.com/page"

    def test_combined_www_slash_tracking(self):
        url = "https://www.example.com/page/?utm_source=google&fbclid=abc"
        result = _normalize_url(url)
        assert result == "https://example.com/page"

    def test_empty_url(self):
        assert _normalize_url("") == ""

    def test_url_without_scheme(self):
        result = _normalize_url("example.com/page")
        assert isinstance(result, str)

    def test_remove_twclid(self):
        """web-core also strips Twitter click IDs."""
        result = _normalize_url("https://example.com?twclid=abc")
        assert "twclid" not in result

    def test_remove_igshid(self):
        """web-core also strips Instagram share IDs."""
        result = _normalize_url("https://example.com?igshid=abc")
        assert "igshid" not in result


# --- _apply_domain_cap tests ---


class TestApplyDomainCap:
    def test_limits_per_domain(self):
        items = [
            {"url": f"https://example.com/page{i}", "title": f"Page {i}"}
            for i in range(5)
        ]
        result = _apply_domain_cap(items)
        assert len(result) == 3

    def test_preserves_diversity(self):
        items = [
            {"url": "https://a.com/1", "title": "A1"},
            {"url": "https://b.com/1", "title": "B1"},
            {"url": "https://a.com/2", "title": "A2"},
            {"url": "https://c.com/1", "title": "C1"},
            {"url": "https://a.com/3", "title": "A3"},
            {"url": "https://a.com/4", "title": "A4"},
            {"url": "https://b.com/2", "title": "B2"},
        ]
        result = _apply_domain_cap(items)
        assert len(result) == 6
        a_count = sum(1 for r in result if "a.com" in r["url"])
        assert a_count == 3

    def test_www_stripped_for_domain_grouping(self):
        items = [
            {"url": "https://www.example.com/1", "title": "1"},
            {"url": "https://example.com/2", "title": "2"},
            {"url": "https://www.example.com/3", "title": "3"},
            {"url": "https://example.com/4", "title": "4"},
        ]
        result = _apply_domain_cap(items)
        assert len(result) == 3

    def test_empty_list(self):
        assert _apply_domain_cap([]) == []

    def test_under_cap_unchanged(self):
        items = [
            {"url": "https://a.com/1", "title": "1"},
            {"url": "https://b.com/1", "title": "2"},
        ]
        result = _apply_domain_cap(items)
        assert len(result) == 2

    def test_preserves_order(self):
        items = [
            {"url": "https://a.com/1", "title": "A1"},
            {"url": "https://b.com/1", "title": "B1"},
            {"url": "https://a.com/2", "title": "A2"},
        ]
        result = _apply_domain_cap(items)
        assert [r["title"] for r in result] == ["A1", "B1", "A2"]


# --- Integration: search() wraps web-core ---


@pytest.fixture(autouse=True)
def mock_health_check():
    with unittest.mock.patch(
        "wet.sources.searxng._ensure_searxng_healthy",
        new_callable=unittest.mock.AsyncMock,
    ) as mock_healthy:
        mock_healthy.side_effect = lambda url: url
        yield mock_healthy


@pytest.fixture
def mock_wc_search():
    """Mock web-core's search function at the delegation boundary."""
    with unittest.mock.patch(
        "wet.sources.searxng._wc_search",
        new_callable=unittest.mock.AsyncMock,
    ) as mock_search:
        yield mock_search


def _make_search_results(count=1):
    """Create mock SearchResult objects (from web-core)."""
    from hull_web.search.models import SearchResult

    return [
        SearchResult(
            url=f"https://example.com/page{i}",
            title=f"Page {i}",
            snippet=f"Content for page {i}",
            source="google",
        )
        for i in range(count)
    ]


async def test_search_returns_json_string(mock_wc_search):
    """search() should convert web-core SearchResults to JSON string."""
    mock_wc_search.return_value = _make_search_results(2)

    result = await search(
        searxng_url="http://localhost:8080",
        query="test query",
        max_results=10,
    )

    data = json.loads(result)
    assert data["total"] == 2
    assert data["query"] == "test query"
    assert len(data["results"]) == 2
    assert data["results"][0]["url"] == "https://example.com/page0"
    assert data["results"][0]["title"] == "Page 0"
    assert data["results"][0]["snippet"] == "Content for page 0"


async def test_search_passes_params_to_hull_web(mock_wc_search):
    """search() should pass all params through to web-core."""
    mock_wc_search.return_value = _make_search_results(1)

    await search(
        searxng_url="http://localhost:8080",
        query="python tutorial",
        categories="images",
        max_results=5,
        time_range="week",
        language="vi",
        include_domains=["docs.python.org"],
        exclude_domains=["pinterest.com"],
    )

    mock_wc_search.assert_called_once_with(
        "http://localhost:8080",
        "python tutorial",
        categories="images",
        max_results=5,
        time_range="week",
        language="vi",
        include_domains=["docs.python.org"],
        exclude_domains=["pinterest.com"],
        auth=None,
    )


async def test_search_error_returns_json_error(mock_wc_search):
    """SearchError should be caught and returned as JSON error string."""
    from hull_web.search import SearchError

    mock_wc_search.side_effect = SearchError("test", "HTTP 500")

    result = await search(
        searxng_url="http://localhost:8080",
        query="test",
    )

    data = json.loads(result)
    assert "error" in data


async def test_search_preserves_original_query(mock_wc_search):
    """Output JSON should contain the original query."""
    mock_wc_search.return_value = _make_search_results(1)

    result = await search(
        searxng_url="http://localhost:8080",
        query="python tutorial",
        include_domains=["docs.python.org"],
    )

    data = json.loads(result)
    assert data["query"] == "python tutorial"


async def test_search_empty_results(mock_wc_search):
    """Empty results from web-core should produce valid JSON."""
    mock_wc_search.return_value = []

    result = await search(
        searxng_url="http://localhost:8080",
        query="obscure query",
    )

    data = json.loads(result)
    assert data["total"] == 0
    assert data["results"] == []


# --- _build_filtered_query tests ---


class TestBuildFilteredQuery:
    def test_no_filters(self):
        assert _build_filtered_query("python tutorial") == "python tutorial"

    def test_include_domains(self):
        result = _build_filtered_query(
            "python", include_domains=["docs.python.org", "realpython.com"]
        )
        assert "site:docs.python.org" in result
        assert "site:realpython.com" in result
        assert "python" in result
        assert " OR " in result

    def test_exclude_domains(self):
        result = _build_filtered_query(
            "python", exclude_domains=["pinterest.com", "quora.com"]
        )
        assert "-site:pinterest.com" in result
        assert "-site:quora.com" in result
        assert result.startswith("python")

    def test_combined_include_exclude(self):
        result = _build_filtered_query(
            "python",
            include_domains=["docs.python.org"],
            exclude_domains=["pinterest.com"],
        )
        assert "site:docs.python.org" in result
        assert "-site:pinterest.com" in result

    def test_include_domains_capped_at_5(self):
        domains = [f"d{i}.com" for i in range(8)]
        result = _build_filtered_query("test", include_domains=domains)
        assert "site:d4.com" in result
        assert "site:d5.com" not in result

    def test_exclude_domains_capped_at_10(self):
        domains = [f"d{i}.com" for i in range(15)]
        result = _build_filtered_query("test", exclude_domains=domains)
        assert "-site:d9.com" in result
        assert "-site:d10.com" not in result

    def test_empty_lists_same_as_none(self):
        assert (
            _build_filtered_query("test", include_domains=[], exclude_domains=[])
            == "test"
        )
