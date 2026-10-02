"""Unit tests for ``wet_mcp.sources._smart_chunks`` post-processor."""

from __future__ import annotations

import pytest

from wet_mcp.sources._smart_chunks import smart_chunks


@pytest.mark.asyncio
async def test_smart_chunks_complete_shape() -> None:
    """Output dict MUST contain all 5 canonical keys."""
    out = smart_chunks(
        "# Hello\n\nworld",
        url="https://example.com",
        strategy_used="basic_http",
        latency_ms=12.5,
    )
    assert set(out.keys()) == {
        "clean_text",
        "markdown",
        "structured_data",
        "code_blocks",
        "metadata",
    }


@pytest.mark.asyncio
async def test_heading_extraction_h1_h2_h3() -> None:
    """Headings H1/H2/H3 are parsed and stored in metadata."""
    md = "# Title\n\n## Sub\n\n### Deep\n\nbody text"
    out = smart_chunks(md, url="https://e.com")
    headings = out["metadata"]["headings"]
    assert {"level": "1", "text": "Title"} in headings
    assert {"level": "2", "text": "Sub"} in headings
    assert {"level": "3", "text": "Deep"} in headings


@pytest.mark.asyncio
async def test_code_block_language_detection() -> None:
    """Fenced code blocks with language hints are labelled, plain becomes 'plain'."""
    md = (
        "intro\n"
        "```python\n"
        "x = 1\n"
        "```\n"
        "mid\n"
        "```bash\n"
        "echo hi\n"
        "```\n"
        "outro\n"
        "```\n"
        "raw\n"
        "```\n"
    )
    out = smart_chunks(md, url="https://e.com")
    blocks = out["code_blocks"]
    assert {"lang": "python", "code": "x = 1"} in blocks
    assert {"lang": "bash", "code": "echo hi"} in blocks
    assert {"lang": "plain", "code": "raw"} in blocks


@pytest.mark.asyncio
async def test_jsonld_parsing_object() -> None:
    """A single JSON-LD object script tag is parsed into structured_data."""
    html = (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Article","headline":"Hi"}'
        "</script></head><body>x</body></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    assert any(
        item.get("@type") == "Article" and item.get("headline") == "Hi"
        for item in out["structured_data"]
    )


@pytest.mark.asyncio
async def test_jsonld_parsing_array() -> None:
    """JSON-LD arrays are flattened into structured_data list."""
    html = (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">'
        '[{"@type":"A","name":"one"},{"@type":"B","name":"two"}]'
        "</script></head><body></body></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    types = sorted(item["@type"] for item in out["structured_data"])
    assert types == ["A", "B"]


@pytest.mark.asyncio
async def test_jsonld_parsing_invalid_json_skipped() -> None:
    """Invalid JSON in ld+json script does NOT raise — it is skipped."""
    html = (
        "<html><head>"
        '<script type="application/ld+json">{not json}</script>'
        '<script type="application/ld+json">{"@type":"OK"}</script>'
        "</head></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    assert any(item.get("@type") == "OK" for item in out["structured_data"])


@pytest.mark.asyncio
async def test_clean_text_strips_html() -> None:
    """clean_text contains visible content with no remaining tags."""
    html = (
        "<html><body><p>Hello <strong>world</strong></p>"
        "<script>alert(1)</script></body></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    assert "Hello" in out["clean_text"]
    assert "<" not in out["clean_text"]
    assert ">" not in out["clean_text"]


@pytest.mark.asyncio
async def test_metadata_includes_strategy_and_latency() -> None:
    """Metadata records strategy name + latency_ms + content_length."""
    out = smart_chunks(
        "body",
        url="https://e.com/page",
        strategy_used="tls_spoof",
        latency_ms=42.0,
    )
    meta = out["metadata"]
    assert meta["scrape_strategy_used"] == "tls_spoof"
    assert meta["latency_ms"] == 42.0
    assert meta["content_length"] == 4
    assert meta["url"] == "https://e.com/page"
    assert meta["source_format"] == "markdown"


@pytest.mark.asyncio
async def test_metadata_html_source_format() -> None:
    """HTML input flips source_format to 'html' + extracts <title>."""
    html = (
        "<!doctype html><html><head><title>My Page</title></head><body>x</body></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    assert out["metadata"]["source_format"] == "html"
    assert out["metadata"]["title"] == "My Page"


@pytest.mark.asyncio
async def test_metadata_title_falls_back_to_h1() -> None:
    """When HTML has no <title>, first H1 in derived markdown becomes title."""
    md = "# First Heading\n\nsome body"
    out = smart_chunks(md, url="https://e.com")
    assert out["metadata"]["title"] == "First Heading"


@pytest.mark.asyncio
async def test_extra_metadata_merged() -> None:
    """Caller-supplied extra_metadata is merged into output metadata."""
    out = smart_chunks(
        "body",
        url="https://e.com",
        extra_metadata={"links_internal": ["a"], "links_external": []},
    )
    assert out["metadata"]["links_internal"] == ["a"]
    assert out["metadata"]["links_external"] == []


@pytest.mark.asyncio
async def test_jsonld_regex_fallback_when_bs4_missing(monkeypatch) -> None:
    """If BeautifulSoup is unavailable, the regex parser still finds JSON-LD blocks."""
    import builtins

    from wet_mcp.sources import _smart_chunks as sc

    real_import = builtins.__import__

    def deny_bs4(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "bs4":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", deny_bs4)
    html = (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">{"@type":"Foo","name":"bar"}</script>'
        '<script type="application/ld+json">[{"@type":"Arr"}]</script>'
        '<script type="application/ld+json">not-json</script>'
        "</head></html>"
    )
    blocks = sc._extract_jsonld(html)
    types = sorted(b.get("@type", "") for b in blocks)
    assert types == ["Arr", "Foo"]


@pytest.mark.asyncio
async def test_html_to_markdown_falls_back_on_markitdown_failure(monkeypatch) -> None:
    """When markitdown raises mid-conversion, the bridge degrades to strip-tags."""
    from wet_mcp.sources import _smart_chunks as sc

    class BadMarkItDown:
        def convert_stream(self, *_, **__):
            raise RuntimeError("converter blew up")

    fake_module = type("M", (), {"MarkItDown": BadMarkItDown})

    import sys

    monkeypatch.setitem(sys.modules, "markitdown", fake_module)

    html = "<html><body><p>Text123</p></body></html>"
    out = sc._html_to_markdown(html)
    assert "Text123" in out
    assert "<" not in out


@pytest.mark.asyncio
async def test_html_to_markdown_falls_back_when_markitdown_missing(monkeypatch) -> None:
    """When markitdown is not installed, fall back to strip-tags too."""
    import builtins

    from wet_mcp.sources import _smart_chunks as sc

    real_import = builtins.__import__

    def deny_markitdown(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "markitdown":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", deny_markitdown)
    out = sc._html_to_markdown("<html><body><span>Hi</span></body></html>")
    assert "Hi" in out
    assert "<" not in out


@pytest.mark.asyncio
async def test_jsonld_array_with_invalid_entries_via_regex(monkeypatch) -> None:
    """Regex fallback skips invalid JSON arrays cleanly without raising."""
    import builtins

    from wet_mcp.sources import _smart_chunks as sc

    real_import = builtins.__import__

    def deny_bs4(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "bs4":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", deny_bs4)
    html = (
        '<script type="application/ld+json">  </script>'  # empty
        '<script type="application/ld+json">[1, 2, 3]</script>'  # array of non-dict
    )
    blocks = sc._extract_jsonld(html)
    assert blocks == []


@pytest.mark.asyncio
async def test_jsonld_bs4_path_handles_invalid_json() -> None:
    """bs4 branch silently skips entries that aren't valid JSON or aren't dicts."""
    html = (
        "<html><head>"
        '<script type="application/ld+json"></script>'
        '<script type="application/ld+json">not-json</script>'
        '<script type="application/ld+json">[1,2,3]</script>'
        '<script type="application/ld+json">{"@type":"OK"}</script>'
        "</head></html>"
    )
    out = smart_chunks(html, url="https://e.com")
    assert any(b.get("@type") == "OK" for b in out["structured_data"])
