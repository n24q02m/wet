"""Markdown and llms.txt heading-aware chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._compat import pkg_attr
from .cleaning import _clean_doc_content

# ---------------------------------------------------------------------------
# Content chunking — split docs into searchable chunks
# ---------------------------------------------------------------------------

# Heading pattern for markdown. No re.MULTILINE: this is matched against one
# line at a time, never against a whole document.
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")


@dataclass
class ChunkContext:
    title: str
    heading_path: str
    url: str


def chunk_markdown(
    content: str,
    url: str = "",
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
) -> list[dict]:
    """Split markdown content into semantic chunks by headings.

    Splits on ## and ### headings, keeping heading hierarchy.
    Chunks that are too large are further split by paragraphs,
    but never inside fenced code blocks.
    """
    if not content or not content.strip():
        return []

    # Clean noise (badges, navigation, footer) before chunking
    content = pkg_attr("_clean_doc_content", _clean_doc_content)(content)
    if not content.strip():
        return []

    chunks: list[dict] = []
    current_title = ""
    heading_path = ""
    current_lines: list[str] = []
    current_length = 0

    def _flush():
        nonlocal current_lines, current_length
        text = "\n".join(current_lines).strip()
        if len(text) >= min_chunk_size:
            # Split oversized chunks by double newline, preserving code blocks
            if len(text) > max_chunk_size:
                ctx = ChunkContext(
                    title=current_title, heading_path=heading_path, url=url
                )
                _split_preserving_code(
                    text,
                    chunks,
                    ctx,
                    max_chunk_size,
                    min_chunk_size,
                )
            else:
                chunks.append(
                    {
                        "content": text,
                        "title": current_title,
                        "heading_path": heading_path,
                        "url": url,
                        "chunk_index": len(chunks),
                    }
                )
        current_lines = []
        current_length = 0

    h1 = ""
    h2 = ""

    for line in content.split("\n"):
        # The prefix test is redundant with the pattern and deliberate: most
        # lines are not headings, and this keeps the regex engine off them.
        heading_match = _HEADING_RE.match(line) if line.startswith("#") else None
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            if level <= 2:
                _flush()
                if level == 1:
                    h1 = heading_text
                    h2 = ""
                else:
                    h2 = heading_text
                current_title = heading_text
                heading_path = f"{h1} > {h2}" if h2 else h1

            elif level <= 4:
                # Flush if current chunk is big enough
                if current_length > max_chunk_size // 2:
                    _flush()
                current_title = heading_text
                heading_path = " > ".join(filter(None, [h1, h2, heading_text]))

        current_length += len(line) + (1 if current_lines else 0)
        current_lines.append(line)

    # Flush remaining
    _flush()

    return chunks


def _split_preserving_code(
    text: str,
    chunks: list[dict],
    context: ChunkContext,
    max_chunk_size: int,
    min_chunk_size: int,
) -> None:
    """Split oversized text by paragraphs without breaking code blocks.

    Groups lines into segments separated by blank lines, but treats
    fenced code blocks (``` ... ```) as atomic units that are never split.
    """
    lines = text.split("\n")
    segments: list[str] = []
    current_segment: list[str] = []
    in_code_block = False

    for line in lines:
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block

        if not in_code_block and line.strip() == "" and current_segment:
            # Paragraph boundary — flush segment
            segments.append("\n".join(current_segment))
            current_segment = []
        else:
            current_segment.append(line)

    if current_segment:
        segments.append("\n".join(current_segment))

    # Merge segments into chunks respecting max_chunk_size
    buffer = ""
    for seg in segments:
        if buffer and len(buffer) + len(seg) + 2 > max_chunk_size:
            buffer_stripped = buffer.strip()
            if buffer_stripped and len(buffer_stripped) >= min_chunk_size:
                chunks.append(
                    {
                        "content": buffer_stripped,
                        "title": context.title,
                        "heading_path": context.heading_path,
                        "url": context.url,
                        "chunk_index": len(chunks),
                    }
                )
            buffer = seg
        else:
            buffer = f"{buffer}\n\n{seg}" if buffer else seg

    buffer_stripped = buffer.strip()
    if buffer_stripped and len(buffer_stripped) >= min_chunk_size:
        chunks.append(
            {
                "content": buffer_stripped,
                "title": context.title,
                "heading_path": context.heading_path,
                "url": context.url,
                "chunk_index": len(chunks),
            }
        )


def chunk_llms_txt(content: str, base_url: str = "") -> list[dict]:
    """Chunk llms.txt / llms-full.txt content.

    llms.txt format uses markdown with clear section headers.
    """
    return pkg_attr("chunk_markdown", chunk_markdown)(
        content, url=base_url, max_chunk_size=2000
    )
