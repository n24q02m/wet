"""Smart-chunks post-processor for ScrapingAgent output.

Converts raw scraping output (HTML or markdown) into a structured dict
with separated text, markdown, JSON-LD structured data, code blocks, and
metadata. Used by the ``extract`` tool dispatcher per spec §4.2.

Output shape::

    {
        "clean_text":     str,            # plain-text strip of HTML / markdown
        "markdown":       str,            # markdown rendition (markitdown bridge)
        "structured_data": list[dict],    # JSON-LD blobs (application/ld+json)
        "code_blocks":    list[dict],     # [{"lang": "python", "code": "..."}]
        "metadata":       dict,           # title, url, scrape_strategy_used,
                                          # latency_ms, content_length, source_format
    }
"""

from __future__ import annotations

import json
import re
from typing import Any

# Pre-compiled regexes
_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _looks_like_html(content: str) -> bool:
    """Heuristic: content contains HTML doctype, <html>, or balanced tags."""
    snippet = content[:4096].lower()
    return (
        "<!doctype html" in snippet
        or "<html" in snippet
        or ("<body" in snippet and "</body" in snippet)
    )


def _html_to_markdown(html: str) -> str:
    """Bridge raw HTML to markdown via markitdown (lazy import).

    Falls back to stripping tags when markitdown is not installed or
    raises an error.
    """
    try:
        import io

        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert_stream(
            io.BytesIO(html.encode("utf-8")), file_extension=".html"
        )
        return result.text_content or ""
    except Exception:
        return _strip_html(html)


def _strip_html(html: str) -> str:
    """Remove HTML tags + collapse whitespace as a clean-text fallback."""
    text = _HTML_TAG_RE.sub(" ", html)
    return " ".join(text.split())


def _extract_jsonld(html: str) -> list[dict[str, Any]]:
    """Find ``<script type="application/ld+json">`` blocks and parse them.

    Uses BeautifulSoup when available; falls back to a regex-only parser
    so the post-processor stays usable without bs4.
    """
    blocks: list[dict[str, Any]] = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                blocks.append(payload)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        blocks.append(item)
        return blocks
    except ImportError:
        # bs4 missing — regex fallback (good enough for well-formed pages).
        pattern = re.compile(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(html):
            raw = match.group(1).strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                blocks.append(payload)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        blocks.append(item)
        return blocks


def _extract_code_blocks(markdown: str) -> list[dict[str, str]]:
    """Pull fenced code blocks ``` ``` from markdown and label by language."""
    blocks: list[dict[str, str]] = []
    for match in _CODE_BLOCK_RE.finditer(markdown):
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2).rstrip("\n")
        blocks.append({"lang": lang or "plain", "code": code})
    return blocks


def _extract_headings(markdown: str) -> list[dict[str, str]]:
    """Parse ATX-style headings (#, ##, ###) from markdown."""
    headings: list[dict[str, str]] = []
    for match in _HEADING_RE.finditer(markdown):
        level = len(match.group(1))
        text = match.group(2).strip()
        headings.append({"level": str(level), "text": text})
    return headings


def _extract_title(html: str, headings: list[dict[str, str]]) -> str:
    """Prefer <title> from HTML, fall back to first H1 heading."""
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL
    )
    if title_match:
        title = " ".join(title_match.group(1).split())
        if title:
            return title
    for heading in headings:
        if heading["level"] == "1":
            return heading["text"]
    return ""


def smart_chunks(
    content: str,
    url: str,
    *,
    strategy_used: str = "",
    latency_ms: float = 0.0,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert raw scrape ``content`` into the structured smart-chunks dict.

    Args:
        content: Raw output from ScrapingAgent (HTML or markdown).
        url: Source URL (recorded in metadata).
        strategy_used: Name of the scraping strategy that produced ``content``.
        latency_ms: Wall-clock time the strategy took (recorded in metadata).
        extra_metadata: Additional metadata to merge into the output.

    Returns:
        Dict with the 5 canonical smart-chunks keys (see module docstring).
    """
    is_html = _looks_like_html(content)
    if is_html:
        markdown = _html_to_markdown(content)
        clean_text = _strip_html(content)
        structured_data = _extract_jsonld(content)
        source_format = "html"
    else:
        markdown = content
        clean_text = " ".join(content.split())
        structured_data = []
        source_format = "markdown"

    headings = _extract_headings(markdown)
    code_blocks = _extract_code_blocks(markdown)
    title = _extract_title(content if is_html else "", headings)

    metadata: dict[str, Any] = {
        "title": title,
        "url": url,
        "scrape_strategy_used": strategy_used,
        "latency_ms": latency_ms,
        "content_length": len(content),
        "source_format": source_format,
        "headings": headings,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return {
        "clean_text": clean_text,
        "markdown": markdown,
        "structured_data": structured_data,
        "code_blocks": code_blocks,
        "metadata": metadata,
    }
