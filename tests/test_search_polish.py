"""Tests for ``wet_mcp.sources._search_polish`` (Phase 1, Task 5).

Covers query normalization, snippet token cap, citation standardization,
freshness signal logic, and TTL policy. All deps are pure stdlib.

Cache TTL expiry round-trip is exercised via ``WebCache.set(ttl_override=...)``
plus ``time.time`` patching to avoid sleeping in unit tests.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wet_mcp.cache import WebCache
from wet_mcp.sources._search_polish import (
    cap_snippet_tokens,
    freshness_signal,
    normalize_query,
    search_ttl_seconds,
    standardize_citation,
    standardize_results,
)

# ---------------------------------------------------------------------------
# normalize_query
# ---------------------------------------------------------------------------


def test_query_expansion_lowercase() -> None:
    assert normalize_query("Python ASYNC Patterns") == "python async patterns"


def test_query_expansion_punctuation_collapsed() -> None:
    # Punctuation -> space, then collapsed.
    assert normalize_query("python!!  async??  patterns?!") == "python async patterns"


def test_query_expansion_keeps_search_meaningful_chars() -> None:
    # Hyphen, dot, quotes and slash are kept (search operators / domains).
    assert normalize_query('"exact phrase" site:github.com -tutorial') == (
        '"exact phrase" site:github.com -tutorial'
    )


def test_query_expansion_empty_input() -> None:
    assert normalize_query("") == ""
    assert normalize_query("   ") == ""


def test_query_expansion_unicode_safe() -> None:
    # Vietnamese diacritics survive lowercase + collapsing.
    assert normalize_query("Đồng bằng sông Cửu Long") == "đồng bằng sông cửu long"


# ---------------------------------------------------------------------------
# cap_snippet_tokens
# ---------------------------------------------------------------------------


def test_snippet_token_cap_200_default() -> None:
    long_snippet = " ".join(f"word{i}" for i in range(500))
    capped = cap_snippet_tokens(long_snippet)
    # 200 tokens kept; ellipsis appended to the last token (no extra split-token).
    tokens = capped.split()
    assert len(tokens) == 200
    assert tokens[-1].endswith("...")
    assert tokens[0] == "word0"


def test_snippet_token_cap_short_snippet_passthrough() -> None:
    short = "this is short"
    assert cap_snippet_tokens(short) == short


def test_snippet_token_cap_empty() -> None:
    assert cap_snippet_tokens("") == ""


def test_snippet_token_cap_custom_limit() -> None:
    snippet = "one two three four five"
    assert cap_snippet_tokens(snippet, max_tokens=2) == "one two..."


# ---------------------------------------------------------------------------
# freshness_signal
# ---------------------------------------------------------------------------


def test_freshness_signal_fresh_no_cache() -> None:
    assert freshness_signal(None, ttl_seconds=3600) == "fresh"


def test_freshness_signal_fresh_within_half_ttl() -> None:
    # 1500s is below half of 3600s.
    assert freshness_signal(1500, ttl_seconds=3600) == "fresh"


def test_freshness_signal_stale_past_half_ttl() -> None:
    # 2000s is above half of 3600s.
    assert freshness_signal(2000, ttl_seconds=3600) == "stale"


def test_freshness_signal_stale_when_ttl_zero() -> None:
    assert freshness_signal(0, ttl_seconds=0) == "stale"


# ---------------------------------------------------------------------------
# standardize_citation
# ---------------------------------------------------------------------------


def test_citation_standardization_format_complete() -> None:
    raw = {
        "title": "How to async in Python",
        "url": "https://realpython.com/async-io-python/",
        "snippet": "Asyncio is a library to write concurrent code.",
    }
    out = standardize_citation(raw, cache_age_seconds=None, ttl_seconds=3600)
    assert out["title"] == "How to async in Python"
    assert out["url"] == "https://realpython.com/async-io-python/"
    assert out["snippet"] == "Asyncio is a library to write concurrent code."
    assert out["source_domain"] == "realpython.com"
    assert out["freshness_signal"] == "fresh"
    # published_at not provided upstream -> not added.
    assert "published_at" not in out


def test_citation_standardization_strips_www() -> None:
    raw = {"title": "T", "url": "https://www.example.com/x", "snippet": "s"}
    out = standardize_citation(raw)
    assert out["source_domain"] == "example.com"


def test_citation_standardization_handles_missing_fields() -> None:
    raw: dict = {"url": "https://example.com"}
    out = standardize_citation(raw)
    assert out["title"] == ""
    assert out["snippet"] == ""
    assert out["source_domain"] == "example.com"


def test_citation_standardization_preserves_extra_keys() -> None:
    raw = {
        "title": "T",
        "url": "https://example.com",
        "snippet": "s",
        "score": 0.95,
        "engine": "google",
    }
    out = standardize_citation(raw)
    assert out["score"] == 0.95
    assert out["engine"] == "google"


def test_citation_standardization_published_at_passthrough() -> None:
    raw = {
        "title": "T",
        "url": "https://example.com",
        "snippet": "s",
        "published_at": "2026-05-01",
    }
    out = standardize_citation(raw)
    assert out["published_at"] == "2026-05-01"


def test_citation_standardization_caps_snippet() -> None:
    long_snippet = " ".join(f"w{i}" for i in range(500))
    raw = {"title": "T", "url": "https://x.com", "snippet": long_snippet}
    out = standardize_citation(raw)
    tokens = out["snippet"].split()
    assert len(tokens) == 200
    assert tokens[-1].endswith("...")


# ---------------------------------------------------------------------------
# freshness signal: fresh vs stale on full result list
# ---------------------------------------------------------------------------


def test_freshness_signal_fresh_vs_stale_in_result_list() -> None:
    raw_results = [
        {"title": "A", "url": "https://a.com", "snippet": "x"},
        {"title": "B", "url": "https://b.com", "snippet": "y"},
    ]
    fresh = standardize_results(raw_results, cache_age_seconds=10, ttl_seconds=3600)
    stale = standardize_results(raw_results, cache_age_seconds=3000, ttl_seconds=3600)
    assert all(r["freshness_signal"] == "fresh" for r in fresh)
    assert all(r["freshness_signal"] == "stale" for r in stale)


# ---------------------------------------------------------------------------
# search_ttl_seconds policy
# ---------------------------------------------------------------------------


def test_search_ttl_300_when_time_range_set() -> None:
    assert search_ttl_seconds("day") == 300
    assert search_ttl_seconds("week") == 300


def test_search_ttl_3600_default() -> None:
    assert search_ttl_seconds(None) == 3600
    assert search_ttl_seconds("") == 3600


# ---------------------------------------------------------------------------
# WebCache TTL expiry round-trip (via time.time patching)
# ---------------------------------------------------------------------------


def test_cache_ttl_expiry(tmp_path) -> None:
    cache = WebCache(tmp_path / "cache.db")
    params = {"q": "x"}

    # time anchor: t=1000.
    with patch("wet_mcp.cache.time.time", return_value=1000.0):
        cache.set("search", params, "payload", ttl_override=300)
        # Within TTL window.
        with patch("wet_mcp.cache.time.time", return_value=1100.0):
            assert cache.get("search", params) == "payload"

    # Past TTL window.
    with patch("wet_mcp.cache.time.time", return_value=1500.0):
        assert cache.get("search", params) is None
    cache.close()


def test_cache_get_with_age_returns_age_seconds(tmp_path) -> None:
    cache = WebCache(tmp_path / "cache.db")
    params = {"q": "y"}

    with patch("wet_mcp.cache.time.time", return_value=2000.0):
        cache.set("search", params, "payload", ttl_override=3600)

    # 600s later, still within TTL.
    with patch("wet_mcp.cache.time.time", return_value=2600.0):
        hit = cache.get_with_age("search", params)
        assert hit is not None
        content, age = hit
        assert content == "payload"
        assert age == 600
    cache.close()


def test_cache_get_with_age_miss_returns_none(tmp_path) -> None:
    cache = WebCache(tmp_path / "cache.db")
    assert cache.get_with_age("search", {"q": "missing"}) is None
    cache.close()


# Pytest sanity: smoke ensure the module imports.
def test_module_imports() -> None:
    import wet_mcp.sources._search_polish as mod  # noqa: F401

    assert mod is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
