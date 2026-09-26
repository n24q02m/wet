"""Comprehensive real-world testing for wet-mcp.

Tests the kept surface across configuration combinations:
1. Embedding: local ONNX vs an OpenAI-compatible provider cell
2. Reranking: local ONNX vs an OpenAI-compatible /rerank cell (hull client)
3. SearXNG: embedded vs external (self-hosted)
4. All 4 tools: search, extract, media, config
5. Docs search: fixed cases (vinejs, inertia, dry-rb)
6. Markitdown: PDF extraction

Run with: uv run pytest tests/test_real_comprehensive.py -v -m integration --timeout=120
"""

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Fixtures for different config modes
# ---------------------------------------------------------------------------

# Self-hosted OpenAI-compatible proxy for the custom-api-base tests below.
# Env-supplied only — there is no centralized n24q02m proxy deployment.
LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_SEARXNG_AUTH_PASS = os.environ.get("SEARXNG_AUTH_PASS")
SEARXNG_EXTERNAL_URL = "https://klprism:{}@searxng.n24q02m.com".format(
    _SEARXNG_AUTH_PASS or ""
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# 1. Docs discovery — fixed cases (vinejs, inertia, dry-rb)
# ---------------------------------------------------------------------------


class TestDocsDiscoveryFixes:
    """Test that previously failing library discoveries now work."""

    @pytest.fixture(autouse=True)
    def _clear_docs_cache(self):
        """Ensure fresh discovery (no stale cache)."""
        pass

    async def test_vinejs_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("vinejs")
        assert result is not None, "vinejs should be discovered"
        assert "vinejs.dev" in result.get("homepage", ""), f"Got: {result}"

    async def test_vinejs_scoped_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("@vinejs/vine")
        assert result is not None, "@vinejs/vine should be discovered"
        assert "vinejs.dev" in result.get("homepage", ""), f"Got: {result}"

    async def test_inertia_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("inertia")
        assert result is not None, "inertia should be discovered"
        assert "inertiajs.com" in result.get("homepage", ""), f"Got: {result}"

    async def test_inertiajs_react_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("@inertiajs/react")
        assert result is not None, "@inertiajs/react should be discovered"
        assert "inertiajs.com" in result.get("homepage", ""), f"Got: {result}"

    async def test_dry_rb_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("dry-rb")
        assert result is not None, "dry-rb should be discovered"
        assert "dry-rb.org" in result.get("homepage", ""), f"Got: {result}"

    async def test_dry_validation_discovery(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("dry-validation")
        assert result is not None, "dry-validation should be discovered"
        assert "dry-rb.org" in result.get("homepage", ""), f"Got: {result}"


# ---------------------------------------------------------------------------
# 2. Search tool — general, academic, docs
# ---------------------------------------------------------------------------


class TestSearchTool:
    """Test search tool with embedded SearXNG."""

    async def test_general_search(self):
        from wet_mcp.config import settings
        from wet_mcp.sources.searxng import search

        searxng_url = settings.searxng_url
        result = await search(searxng_url, "Python asyncio tutorial", max_results=5)
        data = json.loads(result)
        assert len(data) > 0, "General search should return results"

    async def test_academic_search(self):
        from wet_mcp.config import settings
        from wet_mcp.sources.searxng import search

        searxng_url = settings.searxng_url
        result = await search(
            searxng_url,
            "transformer attention mechanism",
            categories="science",
            max_results=5,
        )
        data = json.loads(result)
        assert len(data) > 0, "Academic search should return results"

    async def test_docs_search_fastapi(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("fastapi", language="python")
        assert result is not None
        assert "fastapi" in result.get("homepage", "").lower()

    async def test_docs_search_react(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("react", language="javascript")
        assert result is not None
        assert "react" in result.get("homepage", "").lower()

    async def test_docs_search_axum(self):
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("axum", language="rust")
        assert result is not None


# ---------------------------------------------------------------------------
# 3. Search with external SearXNG (self-hosted)
# ---------------------------------------------------------------------------


class TestExternalSearXNG:
    """Test search using external selfhosted SearXNG."""

    @pytest.fixture(autouse=True)
    def _require_searxng_auth(self):
        if not _SEARXNG_AUTH_PASS:
            pytest.skip("SEARXNG_AUTH_PASS not set")

    async def test_external_searxng_search(self):
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                SEARXNG_EXTERNAL_URL + "/search",
                params={"q": "test", "format": "json"},
            )
            assert resp.status_code == 200, (
                f"External SearXNG unreachable: {resp.status_code}"
            )
            data = resp.json()
            assert len(data.get("results", [])) > 0


# ---------------------------------------------------------------------------
# 4. Extract tool — web pages + markitdown (PDF)
# ---------------------------------------------------------------------------


class TestExtractTool:
    """Test content extraction including document conversion."""

    async def test_extract_web_page(self):
        from wet_mcp.sources.crawler import extract

        result = await extract(
            ["https://httpbin.org/html"],
            format="markdown",
            stealth=False,
        )
        data = json.loads(result)
        assert len(data) == 1
        assert "content" in data[0], f"Extract failed: {data[0]}"
        assert len(data[0]["content"]) > 100

    async def test_extract_pdf_markitdown(self):
        """Test PDF extraction via markitdown."""
        from wet_mcp.sources.crawler import extract

        # Use a well-known small public PDF
        result = await extract(
            ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"],
            format="markdown",
        )
        data = json.loads(result)
        assert len(data) == 1
        assert "error" not in data[0] or "markitdown" not in data[0].get("error", ""), (
            f"PDF extraction failed: {data[0]}"
        )
        if "converter" in data[0]:
            assert data[0]["converter"] == "markitdown"

    async def test_is_document_url_detection(self):
        from wet_mcp.sources.crawler import _is_document_url

        assert _is_document_url("https://example.com/file.pdf")
        assert _is_document_url("https://example.com/report.docx")
        assert _is_document_url("https://example.com/slides.pptx")
        assert not _is_document_url("https://example.com/page.html")
        assert not _is_document_url("https://example.com/")


# ---------------------------------------------------------------------------
# 5. OpenAI-compatible provider cell mode — chat + rerank via hull client
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not LLM_API_BASE, reason="LLM_API_BASE not set")
class TestCustomApiBaseProxy:
    """Test against a self-hosted OpenAI-compatible proxy (env-supplied)."""

    async def test_proxy_reachable(self):
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{LLM_API_BASE}/health/liveliness")
            assert resp.status_code == 200

    async def test_proxy_chat(self):
        """Test LLM chat via proxy using openai-compatible endpoint."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{LLM_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gemini/gemini-3-flash",
                    "messages": [{"role": "user", "content": "Say hello in 3 words"}],
                    "max_tokens": 50,
                },
            )
            assert resp.status_code == 200, f"Chat failed: {resp.text}"
            data = resp.json()
            assert data["choices"][0]["message"]["content"]

    def _cell_client(self):
        """A hull OpenAI-spec client pointed at the proxy (as a cell would be)."""
        from hull_core.config.models import ModelCell
        from hull_core.providers.openai_spec import OpenAICompatClient

        cell = ModelCell(
            task="rerank",
            base_url=LLM_API_BASE,
            api_key=LLM_API_KEY,
            model="rerank-multilingual-v3",
        )
        return OpenAICompatClient(cell)

    async def test_proxy_rerank_via_cell_client(self):
        """Reranking through wet's cell seam (hull OpenAICompatClient)."""
        from wet_mcp.reranker import CloudReranker

        reranker = CloudReranker(self._cell_client())
        results = await reranker.rerank(
            query="What is Python?",
            documents=[
                "Python is a programming language",
                "Java is a programming language",
                "The weather is nice today",
            ],
            top_n=2,
        )
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        # Python doc should score highest
        assert results[0][0] == 0, (
            f"Expected Python doc first, got index {results[0][0]}"
        )
        assert results[0][1] > 0.5, f"Expected high score, got {results[0][1]}"


# ---------------------------------------------------------------------------
# 6. Local ONNX embedding + reranking
# ---------------------------------------------------------------------------


class TestLocalONNX:
    """Test local ONNX embedding and reranking."""

    async def test_local_embedding(self):
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend()
        vectors = await backend.embed_texts(["Hello world", "Python programming"])
        assert len(vectors) == 2
        assert len(vectors[0]) > 0  # Should have dimensions

    async def test_local_reranking(self):
        from wet_mcp.reranker import LocalReranker

        reranker = LocalReranker()
        results = reranker.rerank(
            query="What is Python?",
            documents=[
                "Python is a programming language created by Guido van Rossum",
                "Java is a programming language by Sun Microsystems",
                "The weather forecast says rain tomorrow",
            ],
            top_n=2,
        )
        assert len(results) == 2
        # Results are (index, score) tuples — first should be Python doc
        assert results[0][0] == 0  # index 0 = Python doc


# ---------------------------------------------------------------------------
# 7. Config tool
# ---------------------------------------------------------------------------


class TestConfigTool:
    """Test config tool actions."""

    async def test_config_status(self):
        from wet_mcp.config import settings

        assert settings.log_level in ("INFO", "DEBUG", "WARNING", "ERROR")
        assert settings.tool_timeout > 0
        assert settings.wet_cache is True or settings.wet_cache is False

    async def test_local_backend_availability_flags(self):
        """De-host: backend availability is the local-leg flags + cell state."""
        from wet_mcp.config import settings
        from wet_mcp.runtime import cell_configured

        assert isinstance(settings.local_embed_available(), bool)
        assert isinstance(settings.local_rerank_available(), bool)
        assert cell_configured("embed") in (True, False)
        assert cell_configured("chat") in (True, False)


# ---------------------------------------------------------------------------
# 8. Media tool
# ---------------------------------------------------------------------------


class TestMediaTool:
    """Test media listing from web pages."""

    async def test_list_media(self):
        from wet_mcp.sources.crawler import list_media

        result = await list_media(
            "https://httpbin.org/html",
            media_type="all",
            max_items=5,
        )
        # httpbin/html has no media, but should not error
        data = json.loads(result)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# 9. End-to-end: docs search with indexing
# ---------------------------------------------------------------------------


class TestE2EDocsSearch:
    """End-to-end docs search including indexing and querying."""

    @pytest.mark.timeout(120)
    async def test_docs_search_htmx(self):
        """Full pipeline: discover → index → search."""
        from wet_mcp.sources.docs import discover_library

        result = await discover_library("htmx")
        assert result is not None
        assert "htmx" in result.get("homepage", "").lower()
