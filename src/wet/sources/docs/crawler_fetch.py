"""Sitemap, Sphinx objects.inv, and multi-page documentation fetching."""

from __future__ import annotations

import asyncio
import json
import re
import zlib
from urllib.parse import urljoin, urlparse

from loguru import logger

from ._compat import pkg_attr
from ._http import _is_github_url, _safe_httpx_client
from .cleaning import _is_blocked_content
from .github_raw import _is_i18n_url, _sort_urls_by_query

# ---------------------------------------------------------------------------
# Sitemap discovery — find all docs URLs from sitemap.xml
# ---------------------------------------------------------------------------


async def _try_sitemap(base_url: str, max_urls: int = 50) -> list[str]:
    """Try fetching sitemap.xml and extracting docs page URLs.

    Helps discover pages on SPA sites where link extraction from
    rendered HTML yields only the JS shell page.
    """
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        url = f"{origin}{path}"
        try:
            async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
                timeout=15, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                text = resp.text
                if "<urlset" not in text and "<sitemapindex" not in text:
                    continue

                # Handle sitemap index (links to sub-sitemaps)
                if "<sitemapindex" in text:
                    sub_urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", text)
                    all_page_urls: list[str] = []

                    async def _fetch_sub(sub_url: str) -> list[str]:
                        try:
                            sub_resp = await client.get(sub_url)
                            if sub_resp.status_code == 200:
                                return re.findall(
                                    r"<loc>\s*(.*?)\s*</loc>", sub_resp.text
                                )
                        except Exception:
                            pass
                        return []

                    sub_results = await asyncio.gather(
                        *[_fetch_sub(u) for u in sub_urls[:5]]
                    )
                    for sub_locs in sub_results:
                        all_page_urls.extend(sub_locs)
                    urls = all_page_urls
                else:
                    urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", text)

                # Filter to same domain, skip non-doc paths
                skip_patterns = (
                    "/blog/",
                    "/changelog",
                    "/releases",
                    "/feed",
                    "/rss",
                    "/sitemap",
                    "/robots.txt",
                    "/search",
                    "/genindex",
                    "/searchindex",
                    "/modindex",
                    "/_modules/",
                    "/_sources/",
                )
                filtered = []
                for u in urls:
                    if parsed.netloc not in u:
                        continue
                    u_lower = u.lower()
                    if not any(skip in u_lower for skip in skip_patterns):
                        filtered.append(u)

                if filtered:
                    logger.info(f"Found {len(filtered)} URLs from sitemap at {url}")
                    return filtered[:max_urls]
        except Exception:
            continue

    return []


async def _try_objects_inv(base_url: str, max_urls: int = 50) -> list[str]:
    """Try fetching Sphinx ``objects.inv`` to discover doc page URLs.

    Sphinx-based sites (ReadTheDocs, Pallets, etc.) publish an
    ``objects.inv`` file listing every documented object and its URL.
    This is far more reliable than sitemap.xml for Sphinx sites, which
    often serve a minimal root sitemap with only version-level entries.

    Tries multiple candidate paths to handle cases like boto3 where the
    docs URL is ``/api/`` but objects.inv lives at ``/api/latest/``.
    """
    # Resolve the actual base URL (handle redirects like / -> /en/latest/)
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15, follow_redirects=True
        ) as client:
            resp = await client.get(base_url)
            actual_url = str(resp.url).rstrip("/") + "/"
    except Exception:
        actual_url = base_url.rstrip("/") + "/"

    # Build candidate URLs for objects.inv:
    # 1. At the resolved URL (most common: /en/latest/objects.inv)
    # 2. At /latest/ subdirectory (boto3: /api/latest/objects.inv)
    # 3. At /stable/ subdirectory (some projects use stable by default)
    candidates = [
        f"{actual_url}objects.inv",
        f"{actual_url}latest/objects.inv",
        f"{actual_url}stable/objects.inv",
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15, follow_redirects=True
        ) as client:
            for inv_url in unique_candidates:
                try:
                    resp = await client.get(inv_url)
                except Exception:
                    continue
                if resp.status_code != 200:
                    continue
                data = resp.content
                if not data.startswith(b"# Sphinx inventory version"):
                    continue

                # Determine the base URL for constructing page URLs:
                # objects.inv path minus "objects.inv" = doc root
                inv_base = inv_url.rsplit("objects.inv", 1)[0]

                result = _parse_objects_inv(data, inv_base)
                if result:
                    logger.info(
                        f"Found {len(result)} URLs from objects.inv at {inv_url}"
                    )
                    return result[:max_urls]
    except Exception:
        pass

    return []


def _parse_objects_inv(data: bytes, base_url: str) -> list[str]:
    """Parse Sphinx objects.inv binary data and extract doc page URLs.

    The binary format is:
    - 4 header lines (text)
    - Remaining bytes: zlib-compressed entries
    - Each entry: ``name domain:type priority uri displayname``
    """
    # Find header end (4 newlines)
    header_end = 0
    newline_count = 0
    for i, b in enumerate(data):
        if b == ord("\n"):
            newline_count += 1
            if newline_count == 4:
                header_end = i + 1
                break

    # Decompress rest
    compressed = data[header_end:]
    try:
        decompressed = zlib.decompress(compressed)
        text = decompressed.decode("utf-8", errors="replace")
    except Exception:
        return []

    # Parse entries — only std:doc (pages) and std:label (sections)
    doc_urls: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 4)
        if len(parts) < 4:
            continue
        name = parts[0]
        domain_type = parts[1]
        uri = parts[3]

        if domain_type not in ("std:doc", "std:label"):
            continue
        if uri.endswith("$"):
            uri = name
        # Remove fragment, keep path only
        uri = uri.split("#")[0]
        if not uri or uri.startswith("http"):
            continue
        # Skip non-doc paths
        uri_lower = uri.lower()
        if any(
            skip in uri_lower
            for skip in (
                "changelog",
                "changes",
                "genindex",
                "modindex",
                "searchindex",
                "_modules/",
                "_sources/",
            )
        ):
            continue
        doc_urls.add(f"{base_url}{uri}")

    return sorted(doc_urls)


# ---------------------------------------------------------------------------
# Docs fetching with Crawl4AI
# ---------------------------------------------------------------------------


def _page_from_extract_result(result: dict) -> dict | None:
    """Project one ``crawler.extract`` result into a docs page dict.

    ``extract`` has two result shapes: web pages come back as smart-chunks
    (``markdown`` / ``clean_text`` / ``metadata``), documents come back from
    the markitdown branch (``content`` / ``title``). This crawler only ever
    read the markitdown keys, so every web page failed the truthiness check
    and was discarded — which is why the Tier 1 index produced zero chunks
    for every library. Returns ``None`` for errored or empty results.
    """
    if result.get("error"):
        return None
    content = (
        result.get("markdown")
        or result.get("clean_text")
        or result.get("content")
        or ""
    )
    if not content:
        return None
    metadata = result.get("metadata")
    title = (metadata or {}).get("title") if isinstance(metadata, dict) else None
    return {
        "url": result.get("url", ""),
        "title": title or result.get("title", ""),
        "content": content,
    }


async def fetch_docs_pages(
    docs_url: str,
    query: str = "",
    max_pages: int = 50,
    batch_timeout: int = 45,
) -> list[dict]:
    """Fetch documentation pages from a docs site with depth-2 crawling.

    Strategy:
    1. Fetch the root docs page, extract internal links
    2. Discover more URLs from sitemap.xml
    3. Fetch first batch of pages (round 1)
    4. Extract links from round-1 results (depth-2 discovery)
    5. Fetch second batch from newly discovered URLs (round 2)

    Args:
        batch_timeout: Per-batch crawl timeout in seconds. Each round
            (root, round1, round2) is bounded by this limit.

    Returns list of {url, title, content} dicts.
    """
    from wet.sources.crawler import extract

    # SPA-friendly crawl settings: scroll full page to trigger lazy-loaded
    # content and add a small delay for JS rendering before capture.
    _SPA_KWARGS: dict = {
        "scan_full_page": True,
        "delay_before_return_html": 1.0,
    }

    # Step 1: Fetch root page
    logger.info(f"Fetching docs root: {docs_url}")
    try:
        root_result_str = await asyncio.wait_for(
            extract(urls=[docs_url], format="markdown", stealth=True, **_SPA_KWARGS),
            timeout=batch_timeout,
        )
    except TimeoutError:
        logger.warning(f"Root page fetch timed out after {batch_timeout}s: {docs_url}")
        return []
    root_results = json.loads(root_result_str)

    pages: list[dict] = []
    seen_urls: set[str] = {docs_url}
    pending_urls: list[str] = []

    # For GitHub URLs, restrict crawl to the same repo path
    docs_parsed = urlparse(docs_url)
    _is_github = _is_github_url(docs_url)
    _gh_path_prefix = "/".join(docs_parsed.path.strip("/").split("/")[:2])
    _gh_skip_paths = {
        "features",
        "enterprise",
        "copilot",
        "marketplace",
        "security",
        "sponsors",
        "login",
        "signup",
        "about",
        "pricing",
        "customer-stories",
        "why-github",
    }

    # Generated/index pages to skip (Sphinx, MkDocs, etc.)
    _skip_url_patterns = (
        "/genindex",
        "/searchindex",
        "/modindex",
        "/_modules/",
        "/_sources/",
        "/blog/",
        "/changelog",
        "/releases",
    )
    _skip_url_patterns_re = re.compile(
        "|".join(re.escape(p) for p in _skip_url_patterns)
    )

    # Detect redirect: if actual URL differs from docs_url (e.g., versioned
    # docs), use the redirected path as prefix to restrict crawling to that
    # version.  Prevents crawling sibling version pages (/en/13/, /en/14/).
    _version_prefix = ""
    for r in root_results:
        actual_url = r.get("url", "")
        if actual_url and actual_url != docs_url:
            actual_parsed = urlparse(actual_url)
            if actual_parsed.netloc == docs_parsed.netloc:
                actual_path = actual_parsed.path.rstrip("/")
                actual_parts = [s for s in actual_path.split("/") if s]
                if len(actual_parts) >= 2:
                    _version_prefix = "/" + "/".join(actual_parts) + "/"
                    seen_urls.add(actual_url)
                    logger.info(f"Detected version prefix: {_version_prefix}")
            break

    def _collect_links(result: dict) -> list[str]:
        """Extract valid doc URLs from a crawl result."""
        urls: list[str] = []
        internal = result.get("links", {}).get("internal", [])
        for link in internal:
            href = link.get("href", "") if isinstance(link, dict) else link
            if not href:
                continue
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != docs_parsed.netloc:
                continue
            full_url = urljoin(docs_url, href)
            if full_url in seen_urls:
                continue
            full_parsed = urlparse(full_url)

            # Skip generated index/module pages
            path_lower = full_parsed.path.lower()
            if _skip_url_patterns_re.search(path_lower):
                continue

            # GitHub-specific: stay within same repo
            if _is_github:
                path_parts = full_parsed.path.strip("/").split("/")
                if path_parts and path_parts[0] in _gh_skip_paths:
                    continue
                if "/".join(path_parts[:2]) != _gh_path_prefix:
                    continue

            # Skip translated (non-English) pages
            if _is_i18n_url(full_parsed.path, docs_parsed.path):
                continue

            # Versioned docs: restrict to same version path prefix
            if _version_prefix and not full_parsed.path.startswith(_version_prefix):
                continue

            urls.append(full_url)
            seen_urls.add(full_url)
        return urls

    # Process root page results
    blocked_count = 0
    for r in root_results:
        page = _page_from_extract_result(r)
        if page is None:
            continue
        if _is_blocked_content(page["content"]):
            blocked_count += 1
            continue
        pages.append(page)
        pending_urls.extend(_collect_links(r))

    # Early exit: if root page was blocked, all other pages on the same
    # domain will also be blocked — skip expensive crawling and return
    # empty so that upstream fallback (GitHub raw, configured search) can take over.
    if blocked_count > 0 and not pages:
        logger.warning(
            f"Root page blocked by bot protection, skipping crawl: {docs_url}"
        )
        return pages

    # Sitemap + objects.inv discovery (finds URLs not linked from root page)
    # Run both in parallel — objects.inv is more reliable for Sphinx sites,
    # sitemap.xml works for non-Sphinx sites
    # Bounded by batch_timeout to prevent hanging on slow servers
    sitemap_task = pkg_attr("_try_sitemap", _try_sitemap)(docs_url, max_urls=max_pages)
    inv_task = pkg_attr("_try_objects_inv", _try_objects_inv)(
        docs_url, max_urls=max_pages
    )
    try:
        sitemap_urls, inv_urls = await asyncio.wait_for(
            asyncio.gather(sitemap_task, inv_task),
            timeout=batch_timeout,
        )
    except TimeoutError:
        logger.warning(
            f"Sitemap/objects.inv discovery timed out after {batch_timeout}s"
        )
        sitemap_urls, inv_urls = [], []

    # Merge: objects.inv URLs first (more reliable for Sphinx), then sitemap
    inv_url_set = set(inv_urls)
    extra_urls = list(inv_urls) + [u for u in sitemap_urls if u not in inv_url_set]
    for su in extra_urls:
        su_parsed = urlparse(su)
        if su in seen_urls:
            continue
        if _is_i18n_url(su_parsed.path, docs_parsed.path):
            continue
        # objects.inv URLs already include the correct version path from
        # redirect resolution; only apply version prefix filter to sitemap URLs
        if su not in inv_url_set:
            if _version_prefix and not su_parsed.path.startswith(_version_prefix):
                continue
        pending_urls.append(su)
        seen_urls.add(su)

    # Sort by query relevance
    pending_urls = pkg_attr("_sort_urls_by_query", _sort_urls_by_query)(
        pending_urls, query
    )

    # --- Fetch round 1 ---
    remaining = max_pages - len(pages)
    if remaining > 0 and pending_urls:
        # Reserve some capacity for depth-2 round
        round1_limit = min(len(pending_urls), remaining * 2 // 3 or remaining)
        batch1_urls = pending_urls[:round1_limit]
        pending_urls = pending_urls[round1_limit:]

        logger.info(f"Fetching {len(batch1_urls)} docs pages (round 1)...")
        try:
            batch1_str = await asyncio.wait_for(
                extract(
                    urls=batch1_urls, format="markdown", stealth=True, **_SPA_KWARGS
                ),
                timeout=batch_timeout,
            )
            batch1_results = json.loads(batch1_str)

            for br in batch1_results:
                page = _page_from_extract_result(br)
                if page is None:
                    continue
                if _is_blocked_content(page["content"]):
                    blocked_count += 1
                    continue
                pages.append(page)
                # Depth-2: discover links from fetched pages
                pending_urls.extend(_collect_links(br))
        except TimeoutError:
            logger.warning(
                f"Round 1 crawl timed out after {batch_timeout}s "
                f"({len(batch1_urls)} pages)"
            )

    # --- Fetch round 2 (depth-2 discovery) ---
    remaining = max_pages - len(pages)
    if remaining > 0 and pending_urls:
        pending_urls = pkg_attr("_sort_urls_by_query", _sort_urls_by_query)(
            pending_urls, query
        )
        batch2_urls = pending_urls[:remaining]
        if batch2_urls:
            logger.info(f"Fetching {len(batch2_urls)} docs pages (round 2, depth-2)...")
            try:
                batch2_str = await asyncio.wait_for(
                    extract(
                        urls=batch2_urls, format="markdown", stealth=True, **_SPA_KWARGS
                    ),
                    timeout=batch_timeout,
                )
                batch2_results = json.loads(batch2_str)
                for br in batch2_results:
                    page = _page_from_extract_result(br)
                    if page is None:
                        continue
                    if _is_blocked_content(page["content"]):
                        blocked_count += 1
                        continue
                    pages.append(page)
            except TimeoutError:
                logger.warning(
                    f"Round 2 crawl timed out after {batch_timeout}s "
                    f"({len(batch2_urls)} pages)"
                )

    if blocked_count:
        logger.warning(f"Filtered {blocked_count} bot-protected pages from {docs_url}")
    logger.info(f"Fetched {len(pages)} docs pages from {docs_url}")
    return pages
