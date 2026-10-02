"""Tier-1 integration test for the migrated ``extract`` pipeline (spec §3).

Hits a curated list of popular URLs through the real ``ScrapingAgent``
chain and asserts a relaxed success bar (>=80%) appropriate for the
v1.x.y light fixture (20 URLs vs the 200-URL target tracked by the
spec). The fixture grows pre-Phase 1 release; the bar tightens to
>=95% once the full set lands.

This module is marked ``integration`` + ``slow`` and is excluded from
the default test run (``pyproject.toml::addopts``). Run on demand with::

    uv run pytest -m integration tests/test_extract_tier1_integration.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "urls" / "tier1_popular.txt"


def _load_urls() -> list[str]:
    urls: list[str] = []
    for line in _FIXTURE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_tier1_extract_success_rate() -> None:
    """At least 80% of tier-1 URLs return smart-chunks output without error."""
    from wet_mcp.sources.crawler import extract

    urls = _load_urls()
    assert urls, "tier1_popular.txt fixture is empty"

    raw = await extract(urls)
    pages = json.loads(raw)
    assert len(pages) == len(urls)

    success = [p for p in pages if "error" not in p]
    rate = len(success) / len(pages)
    assert rate >= 0.80, (
        f"tier-1 success rate {rate:.0%} below 80% bar — "
        f"{len(pages) - len(success)} failed of {len(pages)}"
    )

    for page in success:
        for key in (
            "clean_text",
            "markdown",
            "structured_data",
            "code_blocks",
            "metadata",
        ):
            assert key in page, (
                f"missing {key} in smart-chunks output for {page['url']}"
            )
