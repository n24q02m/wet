"""Tests for ``media(action="analyze")`` removal in wet v2.0.0.

Phase 3 Task 5 BREAKING change: analyze action removed entirely after
the 2-minor-version deprecation grace period started in Phase 1 commit
2ea6f23. These tests lock in the removal contract:

- analyze returns the unknown-action error string with a migration hint.
- analyze is NOT in the valid_actions list.
- analyze does NOT invoke wet_mcp.llm.analyze_media (no warning, no work).
- list + download still work (no regression from the removal).
- The docs page no longer advertises analyze as available.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from structured import payload, text

from wet_mcp.server import media


@pytest.mark.asyncio
async def test_media_analyze_returns_unknown_action_error() -> None:
    result = await media(action="analyze", url="/tmp/x.jpg", prompt="hi")
    assert isinstance(result, CallToolResult)
    assert payload(result)["error"].startswith("Error: Unknown action 'analyze'")
    assert "removed in wet v2.0.0" in text(result)
    assert "imagine-mcp" in text(result)


@pytest.mark.asyncio
async def test_media_analyze_does_not_invoke_analyze_media() -> None:
    """Removed action must NOT touch the LLM pipeline."""
    mocked = AsyncMock(return_value="should not run")
    with patch("wet_mcp.llm.analyze_media", mocked):
        result = await media(action="analyze", url="/tmp/x.jpg")
        mocked.assert_not_called()
        assert "Unknown action" in text(result)


@pytest.mark.asyncio
async def test_media_analyze_emits_no_deprecation_warning() -> None:
    """Removal: there is no longer a deprecation warning to emit."""
    with patch("wet_mcp.server.logger") as mock_logger:
        await media(action="analyze")
        # Removal path goes through the unknown-action branch, not the
        # deprecation handler that previously emitted logger.warning.
        assert not mock_logger.warning.called, (
            "removed action must not log a deprecation warning -- "
            "the warning + handler are gone in v2.0.0"
        )


def test_media_help_no_analyze_section() -> None:
    """The docs page must not advertise analyze as an available action."""
    docs_path = Path(__file__).parent.parent / "src" / "wet_mcp" / "docs" / "media.md"
    text = docs_path.read_text(encoding="utf-8")
    # The action must not appear as a top-level "### analyze" with the
    # active phrasing. The "(REMOVED in v2.0.0)" header is allowed and
    # documents the migration path.
    assert "### analyze (REMOVED in v2.0.0)" in text
    assert "### analyze\n" not in text, (
        "docs/media.md must not advertise analyze as an active action"
    )


def test_media_dispatcher_valid_actions_excludes_analyze() -> None:
    """Source-level guard: valid_actions list must not contain 'analyze'."""
    src = inspect.getsource(media)
    # Locate the valid_actions list inside the unknown-action branch.
    assert '"analyze"' not in src.split("valid_actions")[1].split("]")[0], (
        "media valid_actions list must not include 'analyze' in v2.0.0"
    )
    assert '"download"' in src
    assert '"list"' in src


@pytest.mark.asyncio
async def test_media_list_still_works_after_removal() -> None:
    """Backward compat: list keeps its existing contract."""
    with patch(
        "wet_mcp.server.list_media",
        new_callable=AsyncMock,
        return_value='{"images": [{"src": "https://x/y.jpg"}]}',
    ):
        result = await media(action="list", url="https://example.com/gallery")
        assert "images" in text(result)


@pytest.mark.asyncio
async def test_media_download_still_works_after_removal(tmp_path) -> None:
    """Backward compat: download keeps its existing contract."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    with (
        patch("wet_mcp.server.settings.download_dir", str(download_dir)),
        patch(
            "wet_mcp.sources.crawler.download_media",
            new_callable=AsyncMock,
            return_value='[{"url": "https://x/y.jpg", "path": "/tmp/y.jpg"}]',
        ),
    ):
        result = await media(
            action="download",
            media_urls=["https://example.com/img.jpg"],
            output_dir=str(download_dir),
        )
        assert "y.jpg" in text(result)


@pytest.mark.asyncio
async def test_media_unknown_action_default_message() -> None:
    """Non-analyze unknown actions get the standard suggestion message."""
    result = await media(action="bogus_99")
    assert isinstance(result, CallToolResult)
    assert "Unknown action 'bogus_99'" in text(result)
    assert "list" in text(result) and "download" in text(result)


# Sanity import.
def test_module_imports() -> None:
    from wet_mcp import server  # noqa: F401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
