import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from wet_mcp.sources._search_polish import standardize_citation
from wet_mcp.sources.search_backends import run_search_chain


def test_standardize_citation_confidence_exposure():
    # 1. Raw result with score -> exposed as confidence
    raw1 = {
        "url": "https://example.com/1",
        "title": "T1",
        "snippet": "S1",
        "score": 0.85672,
    }
    std1 = standardize_citation(raw1)
    assert std1.get("confidence") == 0.8567

    # 2. Raw result with rerank_score -> exposed as confidence
    raw2 = {
        "url": "https://example.com/2",
        "title": "T2",
        "snippet": "S2",
        "rerank_score": 0.95,
    }
    std2 = standardize_citation(raw2)
    assert std2.get("confidence") == 0.95

    # 3. Raw result without score -> confidence omitted (no fabrication)
    raw3 = {"url": "https://example.com/3", "title": "T3", "snippet": "S3"}
    std3 = standardize_citation(raw3)
    assert "confidence" not in std3

    # 4. Raw result with invalid/NaN score -> confidence omitted
    raw4 = {
        "url": "https://example.com/4",
        "title": "T4",
        "snippet": "S4",
        "score": float("nan"),
    }
    std4 = standardize_citation(raw4)
    assert "confidence" not in std4


@pytest.mark.asyncio
async def test_run_search_chain_parallel_fanout():
    b1 = Mock()
    b1.name = "tavily"
    b1.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {"url": "https://a.com/page1", "title": "A1", "score": 0.9},
                    {
                        "url": "https://shared.com/item",
                        "title": "Shared from Tavily",
                        "score": 0.8,
                    },
                ]
            }
        )
    )

    b2 = Mock()
    b2.name = "brave"
    b2.search = AsyncMock(
        return_value=json.dumps(
            {
                "results": [
                    {
                        "url": "https://shared.com/item",
                        "title": "Shared from Brave",
                        "score": 0.85,
                    },
                    {"url": "https://b.com/page2", "title": "B2", "score": 0.75},
                ]
            }
        )
    )

    with patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b1, b2],
    ):
        with patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=["tavily", "brave"],
        ):
            out_raw = await run_search_chain(
                "test query", max_results=10, parallel=True
            )
            out = json.loads(out_raw)

            # Check deduplication & merged results
            urls = [r["url"] for r in out["results"]]
            assert len(urls) == 3
            assert urls == [
                "https://a.com/page1",
                "https://shared.com/item",
                "https://b.com/page2",
            ]

            # Search backend metadata
            assert out["search_backend"]["fallback"] == "parallel_fanout"
            assert "tavily+brave" in out["search_backend"]["selected"]
            assert out["search_backend"]["attempted"] == ["tavily", "brave"]


@pytest.mark.asyncio
async def test_run_search_chain_parallel_with_one_failure():
    b1 = Mock()
    b1.name = "tavily"
    b1.search = AsyncMock(side_effect=RuntimeError("tavily timeout"))

    b2 = Mock()
    b2.name = "brave"
    b2.search = AsyncMock(
        return_value=json.dumps(
            {"results": [{"url": "https://b.com/page", "title": "B1"}]}
        )
    )

    with patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b1, b2],
    ):
        with patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=["tavily", "brave"],
        ):
            out_raw = await run_search_chain(
                "test query", max_results=10, parallel=True
            )
            out = json.loads(out_raw)

            assert len(out["results"]) == 1
            assert out["results"][0]["url"] == "https://b.com/page"
            assert out["search_backend"]["selected"] == "brave"
            assert out["search_backend"]["fallback"] == "parallel_fanout"


@pytest.mark.asyncio
async def test_run_search_chain_parallel_false_uses_sequential():
    b1 = Mock()
    b1.name = "tavily"
    b1.search = AsyncMock(
        return_value=json.dumps(
            {"results": [{"url": "https://a.com/page1", "title": "A1"}]}
        )
    )

    b2 = Mock()
    b2.name = "brave"
    b2.search = AsyncMock(
        return_value=json.dumps(
            {"results": [{"url": "https://b.com/page2", "title": "B2"}]}
        )
    )

    with patch(
        "wet_mcp.sources.search_backends.search_backends_from_env",
        return_value=[b1, b2],
    ):
        with patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=["tavily", "brave"],
        ):
            out_raw = await run_search_chain(
                "test query", max_results=10, parallel=False
            )
            out = json.loads(out_raw)

            # When parallel=False and b1 succeeds, b2 is not called
            assert len(out["results"]) == 1
            assert out["results"][0]["url"] == "https://a.com/page1"
            assert out["search_backend"]["selected"] == "tavily"
            assert out["search_backend"]["fallback"] == "none"
            b2.search.assert_not_called()
