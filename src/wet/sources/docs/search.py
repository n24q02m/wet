"""High-level documentation resolution, query, and Tier-2 ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._compat import pkg_attr
from ._http import _is_github_url
from .chunking import chunk_markdown
from .crawler_fetch import fetch_docs_pages
from .discovery import discover_library

# ---------------------------------------------------------------------------
# Phase 2: Context7-level docs search primitives.
# ---------------------------------------------------------------------------


def _format_resolved(db: Any, lib_row: dict) -> dict:
    """Project a libraries row into the resolve API shape.

    Picks the most-recently indexed version (if any) as ``latest_version``
    so callers can hand the result straight to ``query_docs``.
    """
    lib_id = lib_row.get("id")
    latest_version: str | None = None
    if lib_id:
        try:
            best = db.get_best_version(lib_id, None)
            if best:
                latest_version = best.get("version")
        except Exception:  # pragma: no cover - defensive
            latest_version = None
    return {
        "library_id": lib_id,
        "name": lib_row.get("name"),
        "canonical_name": lib_row.get("canonical_name") or lib_row.get("name"),
        "tier": lib_row.get("tier"),
        "homepage": lib_row.get("homepage"),
        "github_url": lib_row.get("github_url"),
        "registry": lib_row.get("registry"),
        "description": lib_row.get("description"),
        "latest_version": latest_version,
    }


def resolve_library(db: Any, name: str, limit: int = 5) -> list[dict]:
    """Free-form library name → ranked list of resolved metadata.

    Order:

    1. Exact match on normalized lowercase ``name`` (highest precision).
    2. Prefix match (lib starts with the query) ranked alpha by canonical
       name length (shorter = better).
    3. Substring match anywhere in name (broadest, lowest priority).

    Tier 2 lazy fetch happens later in ``docs_query`` (Task 8). Returning
    an empty list here is intentional for unknown libraries — callers can
    decide to trigger ingestion or surface "not found" to the user.
    """
    if not name or not name.strip():
        return []
    norm = name.lower().strip()
    if not norm:
        return []
    seen_ids: set[str] = set()
    out: list[dict] = []

    exact = db.get_library(norm)
    if exact:
        seen_ids.add(exact["id"])
        out.append(_format_resolved(db, exact))

    if len(out) >= limit:
        return out

    # Prefix match — bounded by limit*4 candidate scan to keep query cheap.
    prefix_rows = db.find_libraries_by_prefix(norm, limit=limit * 4)
    for row in prefix_rows:
        if len(out) >= limit:
            break
        d = dict(row)
        if d["id"] in seen_ids:
            continue
        seen_ids.add(d["id"])
        out.append(_format_resolved(db, d))

    if len(out) >= limit:
        return out

    # Substring fallback (broad). Skip if exact-only requested via limit=1.
    if limit > 1:
        substring_rows = db.find_libraries_by_substring(norm, limit=limit * 4)
        for row in substring_rows:
            if len(out) >= limit:
                break
            d = dict(row)
            if d["id"] in seen_ids:
                continue
            seen_ids.add(d["id"])
            out.append(_format_resolved(db, d))

    return out


# Token budget for docs_query response per spec section 3.
DOCS_QUERY_TOKEN_CAP = 5000


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4) when token_count column is absent.

    Mirrors the OpenAI tiktoken cl100k_base average; deliberately cheap so
    we can honor the spec section 3 token cap without a tiktoken dep.
    """
    return max(1, len(text or "") // 4)


@dataclass
class DocsQueryOptions:
    version: str | None = None
    topic: str | None = None
    limit: int = 10
    query_embedding: list[float] | None = None


def query_docs(
    db: Any,
    library_id: str,
    query: str,
    options: DocsQueryOptions | None = None,
) -> list[dict]:
    """Phase 2 docs query honoring version + topic filter + token cap.

    Steps:

    1. Resolve ``version_id`` via ``DocsDB.get_best_version``. When the
       caller pinned a specific version that is not indexed, return ``[]``
       so the caller can trigger Tier 2 ingestion.
    2. Look up the human-readable library name (FTS path needs it).
    3. Run hybrid search via ``DocsDB.search`` with ``library_name`` +
       ``version`` filter, asking for ``limit*2`` candidates so the topic
       filter has slack.
    4. If ``topic`` is set, drop chunks whose ``topic`` column does not
       match (case-insensitive exact match).
    5. Greedily accumulate chunks until ``sum(token_count) > 5000``,
       falling back to chars/4 estimation when ``token_count`` is NULL.
    """
    if not library_id or not query:
        return []

    opt = options or DocsQueryOptions()

    # Hydrate library + version metadata.
    lib_row = db.get_library_by_id(library_id)
    if lib_row is None:
        return []
    library_name = lib_row["name"]

    if opt.version and opt.version != "latest":
        ver_row = db.get_best_version(library_id, opt.version)
        if ver_row is None or ver_row.get("version") != opt.version:
            # Version not indexed (or only the fallback latest exists) —
            # caller decides whether to trigger ingest.
            return []

    candidates = db.search(
        query=query,
        library_name=library_name,
        version=opt.version if opt.version and opt.version != "latest" else None,
        limit=opt.limit * 2,
        query_embedding=opt.query_embedding,
    )

    if opt.topic:
        norm_topic = opt.topic.lower().strip()
        candidates = [
            c
            for c in candidates
            if (c.get("topic") or "").lower().strip() == norm_topic
        ]

    # Token-budget greedy accumulation per spec section 3.
    out: list[dict] = []
    used_tokens = 0
    for chunk in candidates:
        if len(out) >= opt.limit:
            break
        token_count = chunk.get("token_count")
        if not token_count:
            token_count = _estimate_tokens(chunk.get("content", ""))
        if used_tokens + token_count > DOCS_QUERY_TOKEN_CAP and out:
            break
        out.append(chunk)
        used_tokens += token_count

    return out


async def ingest_tier2(db: Any, library_name: str) -> dict:
    """On-demand Tier 2 ingestion for an unknown library.

    Reuses the existing ``discover_library`` + ``fetch_docs_pages``
    pipeline so we benefit from the GitHub README + RTD/Docusaurus
    detection chain that ship with v1.x. The web-core
    ``library_docs_strategy`` (Task 10) plugs in transparently because
    ``ScrapingAgent`` is the underlying transport.

    Returns ``{"library_id", "version_id", "status", "page_count",
    "chunk_count"}`` so callers can surface a structured progress marker.
    """
    if not library_name:
        return {"status": "error", "error": "library_name required"}

    discovery = await pkg_attr("discover_library", discover_library)(library_name)
    if not discovery:
        return {"status": "not_found", "library_name": library_name}

    # ``discover_library`` publishes the probed docs URL under ``homepage``
    # (see ``_finalize_discovery_result``); no registry adapter ever emits a
    # ``docs_url`` key. Reading only ``docs_url`` therefore always missed and
    # fell through to ``repository``, which npm/PyPI report as a VCS URL
    # (``git+https://...git``) that the crawler rejects as unsafe — every
    # library ingested zero pages.
    docs_url = discovery.get("docs_url") or discovery.get("homepage")
    repo_url = discovery.get("repository") or discovery.get("github_url")
    registry = discovery.get("registry")
    description = discovery.get("description")
    homepage = discovery.get("homepage")
    package_managers = []
    if registry:
        package_managers = [registry]

    # A curated Tier 1 seed can reach this path too: docs_query now fires
    # ingestion for libraries that resolve but hold no indexed version. Keep
    # its tier and display label instead of demoting the row to a Tier 2
    # entry named after the caller's raw query string.
    existing = db.get_library(library_name) or {}
    lib_id = db.upsert_library(
        name=library_name,
        docs_url=docs_url,
        registry=registry,
        description=description,
        tier=existing.get("tier") or 2,
        package_managers=package_managers or None,
        homepage=homepage,
        github_url=repo_url if _is_github_url(repo_url) else None,
        canonical_name=existing.get("canonical_name") or library_name,
    )
    ver_id = db.upsert_version(
        library_id=lib_id,
        version="latest",
        docs_url=docs_url,
    )

    if not docs_url and not repo_url:
        return {
            "status": "no_docs",
            "library_id": lib_id,
            "version_id": ver_id,
            "library_name": library_name,
        }

    target_url = docs_url or repo_url
    if not target_url:
        return {
            "status": "no_docs",
            "library_id": lib_id,
            "version_id": ver_id,
            "library_name": library_name,
        }
    pages = await pkg_attr("fetch_docs_pages", fetch_docs_pages)(target_url, "")
    chunks_added = 0
    if pages:
        chunks: list[dict] = []
        for page in pages:
            # chunk_markdown's third parameter is max_chunk_size, not title —
            # passing the page title there raised TypeError. It never fired
            # because `pages` was always empty (see _page_from_extract_result).
            page_chunks = pkg_attr("chunk_markdown", chunk_markdown)(
                page["content"], url=page.get("url", "")
            )
            chunks.extend(page_chunks)
        if chunks:
            db.add_chunks(version_id=ver_id, library_id=lib_id, chunks=chunks)
            chunks_added = len(chunks)
            db.mark_version_indexed(ver_id, len(pages), chunks_added)
            db.mark_library_indexed(lib_id, total_versions=1)

    return {
        "status": "ok" if chunks_added else "no_chunks",
        "library_id": lib_id,
        "version_id": ver_id,
        "library_name": library_name,
        "page_count": len(pages or []),
        "chunk_count": chunks_added,
    }
