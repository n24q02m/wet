"""Crawl + extract integration.

The ``extract`` action now delegates to ``web_core.scraper.ScrapingAgent``
(5-strategy chain: ``basic_http`` → ``tls_spoof`` → ``api_direct`` →
``headless`` → ``patchright``, plus optional ``captcha``). Phase 1 spec
§4.2/§5.5: drop direct Crawl4AI usage from the extract path; consume
web-core primitives so escalation, robots.txt + selector-inference are
shared with sibling consumers.

The ``crawl``, ``sitemap``, ``list_media`` paths still rely on the legacy
Crawl4AI singleton browser pool for now (Phase 1 keeps wet-local media;
crawl + sitemap migration is out of scope for v1.x.y per spec §5.7
contribute-back roadmap). Crawl4AI is reached via ``web_core``'s
transitive dependency, so we no longer require a direct
``crawl4ai`` entry in ``pyproject.toml``.
"""

import asyncio
import collections
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from loguru import logger
from web_core.scraper import ScrapingAgent
from web_core.scraper.strategies import (
    BasicHTTPStrategy,
    HeadlessStrategy,
    TLSSpoofStrategy,
)

from wet_mcp.config import settings
from wet_mcp.security import is_safe_url
from wet_mcp.security import safe_httpx_client as _safe_httpx_client
from wet_mcp.sources._smart_chunks import smart_chunks

# Document extensions that markitdown handles better than Crawl4AI
_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls"}
_DOCUMENT_EXTENSIONS_TUPLE = tuple(_DOCUMENT_EXTENSIONS)

_MAX_CONVERT_FILES = 10

_LOCAL_CONVERT_EXTENSIONS = _DOCUMENT_EXTENSIONS | {
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".epub",
    ".txt",
    ".md",
    ".rst",
    ".log",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
}

# ---------------------------------------------------------------------------
# Browser pool (singleton)
# ---------------------------------------------------------------------------

# Per-process browser data directory to prevent Playwright lock deadlock
# when multiple MCP server instances run simultaneously.
_BROWSER_DATA_DIR = str(Path(tempfile.gettempdir()) / f"wet-mcp-browser-{os.getpid()}")

# Maximum number of concurrent browser operations.  Each operation uses a
# tab/page inside the shared browser, so we can safely allow several in
# parallel without starting extra browser processes.
_MAX_CONCURRENT_OPS = 6

# Guards all access to the shared crawler instance.
_pool_lock = asyncio.Lock()
_crawler_instance: AsyncWebCrawler | None = None
_crawler_stealth: bool = False  # stealth mode of the current instance

# Semaphore to limit concurrent browser operations across all callers.
_browser_semaphore: asyncio.Semaphore | None = None


def _browser_config(stealth: bool = False) -> BrowserConfig:
    """Create BrowserConfig with per-process isolated data directory."""
    extra_args: list[str] = []

    # Docker/CI/Cloudflare-Containers environments need --no-sandbox (Chromium
    # cannot use the SUID sandbox inside unprivileged containers). CF Containers
    # do not create the ``/.dockerenv`` marker nor set ``container``, so fall
    # back to the HTTP-transport signal (any HTTP daemon deployment is a
    # container) to keep chromium launchable there.
    from wet_mcp.transport_check import _is_http_transport

    if (
        os.path.exists("/.dockerenv")
        or os.environ.get("container")
        or _is_http_transport()
    ):
        extra_args += ["--no-sandbox", "--disable-dev-shm-usage"]

    return BrowserConfig(
        headless=True,
        enable_stealth=stealth,
        verbose=False,
        user_data_dir=_BROWSER_DATA_DIR,
        extra_args=extra_args,
    )


def _get_semaphore() -> asyncio.Semaphore:
    """Return the module-level semaphore, creating it lazily.

    The semaphore is created lazily because it must be bound to the
    running event loop at creation time.
    """
    global _browser_semaphore
    if _browser_semaphore is None:
        _browser_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_OPS)
    return _browser_semaphore


def _crawler_run_config() -> CrawlerRunConfig:
    """Build the shared Crawl4AI run policy for legacy crawler actions."""
    return CrawlerRunConfig(
        verbose=False,
        check_robots_txt=settings.respect_robots_txt,
    )


def _cleanup_browser_data_dir() -> None:
    """Remove browser data directory to clear stale locks and state."""
    import shutil

    try:
        data_dir = Path(_BROWSER_DATA_DIR)
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            logger.debug(f"Cleaned browser data dir: {data_dir}")
    except Exception as exc:
        logger.debug(f"Error cleaning browser data dir: {exc}")


async def _get_crawler(stealth: bool = False) -> AsyncWebCrawler:
    """Return a shared AsyncWebCrawler, creating one if necessary.

    If the requested *stealth* mode differs from the current instance the
    old browser is shut down and a new one is started.  This should rarely
    happen in practice since most calls use the same stealth setting.

    On failure (e.g. Playwright connection corrupted after browser recycle),
    retries once with a fresh browser data directory.
    """
    global _crawler_instance, _crawler_stealth

    async with _pool_lock:
        # Reuse existing instance if stealth matches
        if _crawler_instance is not None and _crawler_stealth == stealth:
            return _crawler_instance

        # Tear down existing instance with different stealth mode
        if _crawler_instance is not None:
            logger.debug(f"Recycling browser (stealth {_crawler_stealth} -> {stealth})")
            try:
                await _crawler_instance.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug(f"Error closing old crawler: {exc}")
            _crawler_instance = None

        # Start a fresh browser (retry once on failure)
        for attempt in range(2):
            logger.info(f"Starting shared browser (stealth={stealth})...")
            crawler = AsyncWebCrawler(
                verbose=False,
                config=_browser_config(stealth),
            )
            try:
                await crawler.__aenter__()
                _crawler_instance = crawler
                _crawler_stealth = stealth
                logger.info("Shared browser started")
                return _crawler_instance
            except Exception:
                if attempt == 0:
                    logger.warning(
                        "Browser start failed, retrying with fresh data dir..."
                    )
                    _cleanup_browser_data_dir()
                else:
                    logger.error("Failed to start shared browser after retry")
                    raise

        raise RuntimeError("Failed to start shared browser")


async def shutdown_crawler() -> None:
    """Shut down the shared browser (called during server shutdown)."""
    global _crawler_instance, _browser_semaphore, _scraping_agent

    async with _pool_lock:
        if _crawler_instance is not None:
            logger.info("Shutting down shared browser...")
            try:
                await _crawler_instance.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug(f"Error during browser shutdown: {exc}")
            _crawler_instance = None
            logger.info("Shared browser shut down")
        _browser_semaphore = None
        _scraping_agent = None


# ---------------------------------------------------------------------------
# ScrapingAgent (web-core) singleton — used by extract()
# ---------------------------------------------------------------------------

_scraping_agent: ScrapingAgent | None = None
_agent_lock = asyncio.Lock()


def _build_headless_strategies(stealth: bool) -> dict[str, Any]:
    """Resolve the BROWSER_BACKENDS chain into named headless strategies.

    Each headless backend (native chromium / self-host browserless) enters the
    agent chain as its own strategy, so the agent's existing
    escalate-on-validation-failure machinery provides runtime fallback between
    them (e.g. a 5xx/timeout on native advances to browserless).
    Backends whose credentials are missing are skipped with a warning. If the
    chain resolves to nothing AND local browser is NOT disabled, fall back to
    native so local extraction keeps a JS-render escalation; if local IS
    disabled with no cloud creds, the headless leg is intentionally absent
    (extract degrades to basic_http/tls_spoof).
    """
    from web_core.browsers import BrowserlessClient
    from web_core.scraper.strategies import RemoteRenderStrategy

    out: dict[str, Any] = {}
    for backend in settings.browser_backend_chain():
        try:
            if backend == "native":
                out["headless"] = HeadlessStrategy(
                    timeout=settings.crawler_timeout, stealth=stealth
                )
            elif backend == "browserless":
                client = BrowserlessClient(
                    settings.browserless_url,
                    token=settings.browserless_token,
                    timeout=settings.crawler_timeout,
                )
                out["browserless"] = RemoteRenderStrategy(client)
            else:
                logger.warning(f"Unknown browser backend {backend!r}; skipping")
        except ValueError as exc:
            logger.warning(f"Skipping browser backend {backend!r}: {exc}")
    if not out and not settings.disable_local_browser:
        out["headless"] = HeadlessStrategy(
            timeout=settings.crawler_timeout, stealth=stealth
        )
    return out


def _build_scraping_agent(stealth: bool = True) -> ScrapingAgent:
    """Build a ScrapingAgent with the canonical wet strategy chain.

    Order matches spec §4.2 escalation: ``basic_http`` → ``tls_spoof`` → the
    headless provider chain (``native`` / ``browserless``, resolved from
    BROWSER_BACKENDS). ``api_direct``/
    ``patchright`` are intentionally omitted (api_direct rarely beats basic_http
    on arbitrary URLs; patchright pulls in heavier optional deps); ``captcha`` is
    appended separately as a key-gated tier (see _build_scraping_agent callers).

    ``respect_robots`` follows ``RESPECT_ROBOTS_TXT``. The setting defaults to
    False to preserve wet's historical behaviour for existing deployments.
    """
    strategies: dict[str, Any] = {
        "basic_http": BasicHTTPStrategy(timeout=settings.crawler_timeout),
        "tls_spoof": TLSSpoofStrategy(timeout=settings.crawler_timeout),
    }
    strategies.update(_build_headless_strategies(stealth))
    # Optional, key-gated CAPTCHA tier: appended LAST so it is only reached after
    # the lighter strategies fail validation (e.g. on a Cloudflare Turnstile).
    # Lazy-imported so the heavier CapSolver/patchright path loads only when a key
    # is set. Solves the captcha layer only, not IP reputation.
    if settings.capsolver_api_key:
        from web_core.scraper.strategies import CaptchaStrategy

        strategies["captcha"] = CaptchaStrategy(
            capsolver_api_key=settings.capsolver_api_key
        )
    return ScrapingAgent(
        strategies=strategies,
        respect_robots=settings.respect_robots_txt,
    )


async def _get_scraping_agent(stealth: bool = True) -> ScrapingAgent:
    """Return a process-wide ScrapingAgent, building one on first use."""
    global _scraping_agent
    async with _agent_lock:
        if _scraping_agent is None:
            logger.info("Initialising web-core ScrapingAgent")
            _scraping_agent = _build_scraping_agent(stealth=stealth)
        return _scraping_agent


# ---------------------------------------------------------------------------
# Document conversion (markitdown)
# ---------------------------------------------------------------------------


def _is_document_url(url: str) -> bool:
    """Check if URL points to a document file (PDF, DOCX, etc.)."""
    path = urlparse(url).path.lower()
    return path.endswith(_DOCUMENT_EXTENSIONS_TUPLE)


def _detect_document_content_type(content_type: str) -> bool:
    """Check if HTTP Content-Type indicates a document file."""
    doc_types = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/msword",
        "application/vnd.ms-powerpoint",
        "application/vnd.ms-excel",
    )
    return content_type.startswith(doc_types)


async def _extract_with_markitdown(url: str) -> dict:
    """Download document and convert to Markdown via markitdown."""
    try:
        from markitdown import MarkItDown
    except ImportError:
        return {
            "url": url,
            "error": "markitdown not installed. Install with: pip install 'markitdown[pdf,docx,pptx]'",
        }

    try:
        async with _safe_httpx_client(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        # Write to temp file (markitdown needs file path with extension)
        import io

        ext = Path(urlparse(url).path).suffix.lower() or ".pdf"
        md = MarkItDown()
        result = await asyncio.to_thread(
            md.convert_stream, io.BytesIO(resp.content), file_extension=ext
        )

        return {
            "url": url,
            "title": Path(urlparse(url).path).stem,
            "content": result.text_content,
            "converter": "markitdown",
        }
    except Exception as e:
        logger.error(f"markitdown failed for {url}: {e}")
        return {"url": url, "error": f"Document conversion failed: {e}"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract(
    urls: list[str],
    format: str = "markdown",
    stealth: bool = True,
    scan_full_page: bool = False,
    delay_before_return_html: float = 0.0,
    page_timeout: int = 60000,
) -> str:
    """Extract content from URLs via web-core ``ScrapingAgent``.

    The agent walks a 3-strategy chain (``basic_http`` → ``tls_spoof`` →
    ``headless``) with cache-recommended ordering and LLM selector
    inference fallback. Output is post-processed into smart-chunks dicts
    (``clean_text`` / ``markdown`` / ``structured_data`` / ``code_blocks``
    / ``metadata``) per spec §4.2.

    Args:
        urls: List of URLs to extract.
        format: Reserved for future use (smart-chunks always emit both
            markdown and clean_text). Accepted for backward compat.
        stealth: Forwarded to the headless strategy when the agent is
            built; ignored for already-instantiated agents.
        scan_full_page: Reserved (no-op under ScrapingAgent — escalation
            now relies on strategy chain rather than scroll injection).
        delay_before_return_html: Reserved (no-op).
        page_timeout: Reserved (no-op; per-strategy timeouts apply).

    Returns:
        JSON string of smart-chunks dicts (one per URL). Failed URLs
        produce ``{"url": ..., "error": "..."}`` entries.
    """
    del format, scan_full_page, delay_before_return_html, page_timeout  # reserved

    logger.info(f"Extracting content from {len(urls)} URLs via ScrapingAgent")

    agent = await _get_scraping_agent(stealth=stealth)
    sem = _get_semaphore()

    async def process_url(url: str) -> dict[str, Any]:
        async with sem:
            if not is_safe_url(url):
                logger.warning(f"Skipping unsafe URL: {url}")
                return {"url": url, "error": "Security Alert: Unsafe URL blocked"}

            if _is_document_url(url):
                logger.info(f"Document URL detected, using markitdown: {url}")
                return await _extract_with_markitdown(url)

            try:
                t0 = asyncio.get_event_loop().time()
                content = await agent.scrape(url)
                latency_ms = (asyncio.get_event_loop().time() - t0) * 1000.0
            except Exception as e:
                logger.error(f"Error extracting {url}: {e}")
                return {"url": url, "error": str(e)}

            strategy_used = ""
            try:
                cache_recs = await agent.strategy_cache.recommend(url)
                if cache_recs:
                    strategy_used = cache_recs[0]
            except Exception:
                pass

            chunks = smart_chunks(
                content,
                url=url,
                strategy_used=strategy_used,
                latency_ms=latency_ms,
            )
            return {"url": url, **chunks}

    tasks = [process_url(url) for url in urls]
    results = await asyncio.gather(*tasks)

    logger.info(f"Extracted {len(results)} pages")
    return json.dumps(results, ensure_ascii=False, indent=2)


async def crawl(
    urls: list[str],
    depth: int = 2,
    max_pages: int = 20,
    format: str = "markdown",
    stealth: bool = True,
) -> str:
    """Deep crawl from root URLs.

    Args:
        urls: List of root URLs
        depth: Crawl depth
        max_pages: Maximum pages to crawl
        format: Output format
        stealth: Enable stealth mode

    Returns:
        JSON string with crawled content
    """
    logger.info(f"Crawling {len(urls)} URLs with depth={depth}")

    all_results = []
    visited: set[str] = set()

    crawler = await _get_crawler(stealth)
    sem = _get_semaphore()

    for root_url in urls:
        if not is_safe_url(root_url):
            logger.warning(f"Skipping unsafe URL: {root_url}")
            continue

        # Use deque for O(1) pops (BFS)
        to_crawl: collections.deque[tuple[str, int]] = collections.deque(
            [(root_url, 0)]
        )

        while to_crawl and len(all_results) < max_pages:
            url, current_depth = to_crawl.popleft()

            if url in visited or current_depth > depth:
                continue

            # Validate every URL (not just root) to prevent SSRF
            # via malicious internal links on attacker-controlled pages
            if not is_safe_url(url):
                logger.warning(f"Skipping unsafe discovered URL: {url}")
                continue

            visited.add(url)

            async with sem:
                try:
                    result = await crawler.arun(  # ty: ignore[missing-argument]
                        url,  # type: ignore[invalid-argument-type]  # ty: ignore[invalid-argument-type]
                        config=_crawler_run_config(),
                    )

                    if result.success:
                        content = (
                            result.markdown
                            if format == "markdown"
                            else result.cleaned_html
                        )
                        all_results.append(
                            {
                                "url": url,
                                "depth": current_depth,
                                "title": result.metadata.get("title", ""),
                                "content": content[:5000],  # Limit content size
                            }
                        )

                        # Add internal links for next depth
                        if current_depth < depth:
                            internal_links = result.links.get("internal", [])
                            for link_item in internal_links[:10]:
                                # Crawl4AI returns dicts with 'href' key
                                link_url = (
                                    link_item.get("href", "")
                                    if isinstance(link_item, dict)
                                    else link_item
                                )
                                if link_url and link_url not in visited:
                                    to_crawl.append((link_url, current_depth + 1))

                except Exception as e:
                    logger.error(f"Error crawling {url}: {e}")

    logger.info(f"Crawled {len(all_results)} pages")
    return json.dumps(all_results, ensure_ascii=False, indent=2)


async def sitemap(
    urls: list[str],
    depth: int = 2,
    max_pages: int = 50,
) -> str:
    """Discover site structure.

    Args:
        urls: List of root URLs
        depth: Discovery depth
        max_pages: Maximum pages to discover

    Returns:
        JSON string with discovered URLs
    """
    logger.info(f"Mapping {len(urls)} URLs")

    all_urls: list[dict[str, object]] = []
    visited: set[str] = set()

    crawler = await _get_crawler(stealth=False)
    sem = _get_semaphore()

    for root_url in urls:
        if not is_safe_url(root_url):
            logger.warning(f"Skipping unsafe URL: {root_url}")
            continue

        # Use deque for O(1) pops (BFS)
        to_visit: collections.deque[tuple[str, int]] = collections.deque(
            [(root_url, 0)]
        )
        site_urls: list[dict[str, object]] = []

        while to_visit and len(site_urls) < max_pages:
            url, current_depth = to_visit.popleft()

            if url in visited or current_depth > depth:
                continue

            # Validate every URL (not just root) to prevent SSRF
            if not is_safe_url(url):
                logger.warning(f"Skipping unsafe discovered URL: {url}")
                continue

            visited.add(url)
            site_urls.append({"url": url, "depth": current_depth})

            async with sem:
                try:
                    result = await crawler.arun(  # ty: ignore[missing-argument]
                        url,  # type: ignore[invalid-argument-type]  # ty: ignore[invalid-argument-type]
                        config=_crawler_run_config(),
                    )

                    if settings.respect_robots_txt and not result.success:
                        site_urls.pop()
                        continue

                    if result.success and current_depth < depth:
                        for link in result.links.get("internal", [])[:20]:
                            # Extract URL from dict if necessary
                            link_url = (
                                link.get("href", "") if isinstance(link, dict) else link
                            )
                            if link_url and link_url not in visited:
                                to_visit.append((link_url, current_depth + 1))

                except Exception as e:
                    logger.debug(f"Error mapping {url}: {e}")

        all_urls.extend(site_urls)

    logger.info(f"Mapped {len(all_urls)} URLs")
    return json.dumps(all_urls, ensure_ascii=False, indent=2)


async def list_media(
    url: str,
    media_type: str = "all",
    max_items: int = 10,
) -> str:
    """List media from a page.

    Args:
        url: Page URL to scan
        media_type: Type of media (images, videos, audio, files, all)
        max_items: Maximum items to return

    Returns:
        JSON string with media list
    """
    logger.info(f"Listing media from: {url}")

    if not is_safe_url(url):
        return json.dumps({"error": "Security Alert: Unsafe URL blocked"})

    crawler = await _get_crawler(stealth=False)
    sem = _get_semaphore()

    async with sem:
        result = await crawler.arun(  # ty: ignore[missing-argument]
            url,  # type: ignore[invalid-argument-type]  # ty: ignore[invalid-argument-type]
            config=_crawler_run_config(),
        )

        if not result.success:
            return json.dumps({"error": result.error_message or "Failed to load page"})

        media = result.media or {}

        output: dict[str, list] = {}

        if media_type in ("images", "all"):
            output["images"] = media.get("images", [])[:max_items]
        if media_type in ("videos", "all"):
            output["videos"] = media.get("videos", [])[:max_items]
        if media_type in ("audio", "all"):
            # Crawl4AI uses 'audios' (plural)
            output["audio"] = media.get("audios", [])[:max_items]

        logger.info(f"Found media: {sum(len(v) for v in output.values())} items")
        return json.dumps(output, ensure_ascii=False, indent=2)


async def download_media(
    media_urls: list[str],
    output_dir: str,
    concurrency: int = 5,
) -> str:
    """Download media files.

    Args:
        media_urls: List of media URLs to download
        output_dir: Output directory
        concurrency: Max concurrent downloads

    Returns:
        JSON string with download results
    """
    logger.info(f"Downloading {len(media_urls)} media files")

    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    semaphore = asyncio.Semaphore(concurrency)

    async def _download_one(url: str, client: httpx.AsyncClient) -> dict:
        async with semaphore:
            try:
                # Handle protocol-relative URLs
                target_url = url
                if target_url.startswith("//"):
                    target_url = f"https:{target_url}"

                # Manually handle redirects to prevent SSRF bypass
                redirect_count = 0
                max_redirects = 5
                response = None

                while redirect_count < max_redirects:
                    if not is_safe_url(target_url):
                        return {
                            "url": url,
                            "error": "Security Alert: Unsafe URL blocked",
                        }

                    response = await client.get(target_url, follow_redirects=False)

                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            break
                        target_url = urljoin(target_url, location)
                        redirect_count += 1
                        continue
                    else:
                        break

                if not response:
                    raise ValueError("No response received")

                response.raise_for_status()

                # Extract filename and decode URL-encoded characters to
                # prevent path traversal via %2F..%2F sequences.
                import mimetypes
                from urllib.parse import unquote

                raw_name = target_url.split("/")[-1].split("?")[0] or "download"
                decoded_name = unquote(raw_name)
                # Strip any directory components to get a flat filename
                filename = Path(decoded_name).name or "download"

                # If filename has no extension, infer from Content-Type
                if "." not in filename:
                    content_type = response.headers.get("content-type", "")
                    # Strip parameters like charset
                    mime = content_type.split(";")[0].strip()
                    ext = mimetypes.guess_extension(mime) if mime else None
                    if ext:
                        filename = f"{filename}{ext}"
                filepath = (output_path / filename).resolve()

                # Security check: Ensure the resolved path is still
                # within the output directory
                if not filepath.is_relative_to(output_path):
                    raise ValueError(
                        f"Security Alert: Path traversal attempt detected "
                        f"for {filename}"
                    )

                # Write file in thread to avoid blocking event loop
                await asyncio.to_thread(filepath.write_bytes, response.content)

                return {
                    "url": url,
                    "path": str(filepath),
                    "size": len(response.content),
                }

            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")
                return {
                    "url": url,
                    "error": str(e),
                }

    async with _safe_httpx_client(
        timeout=settings.crawler_timeout, headers=headers
    ) as client:
        tasks = [_download_one(url, client) for url in media_urls]
        results = await asyncio.gather(*tasks)

    logger.info(f"Downloaded {len([r for r in results if 'path' in r])} files")
    return json.dumps(results, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Batch extraction with per-domain rate limiting
# ---------------------------------------------------------------------------


class DomainRateLimiter:
    """Per-domain concurrency + rate limiting for batch operations."""

    def __init__(
        self,
        max_per_domain: int = 2,
        requests_per_second: float = 1.0,
        global_max: int = 10,
    ):
        from collections import defaultdict

        from aiolimiter import AsyncLimiter

        self._domain_sems: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(max_per_domain)
        )
        self._domain_limiters: dict[str, AsyncLimiter] = defaultdict(
            lambda: AsyncLimiter(requests_per_second, 1)
        )
        self._global_sem = asyncio.Semaphore(global_max)

    @asynccontextmanager
    async def acquire(self, url: str):
        domain = urlparse(url).netloc
        async with self._global_sem:
            async with self._domain_sems[domain]:
                await self._domain_limiters[domain].acquire()
                yield


_MAX_BATCH_URLS = 50


async def batch_extract(
    urls: list[str],
    format: str = "markdown",
    stealth: bool = False,
) -> str:
    """Batch extract content from URLs with per-domain rate limiting.

    Uses DomainRateLimiter for polite crawling: max 2 concurrent per domain,
    1 req/s per domain, 10 global concurrent. Partial results on failure.

    Args:
        urls: List of URLs (max 50)
        format: Output format
        stealth: Enable stealth mode

    Returns:
        JSON with {results, errors, summary: {total, success, failed}}
    """
    if len(urls) > _MAX_BATCH_URLS:
        return f"Error: Maximum {_MAX_BATCH_URLS} URLs per batch (got {len(urls)})"

    limiter = DomainRateLimiter()
    results: list[dict] = []
    errors: list[dict] = []

    async def process_url(url: str) -> dict:
        async with limiter.acquire(url):
            try:
                raw = await extract(urls=[url], format=format, stealth=stealth)
                pages = json.loads(raw)
                if pages and isinstance(pages, list):
                    return pages[0]
                return {"url": url, "error": "Empty result"}
            except Exception as e:
                return {"url": url, "error": str(e)}

    # Process with as_completed for partial results
    tasks = {asyncio.create_task(process_url(url)): url for url in urls}

    for coro in asyncio.as_completed(tasks):
        result = await coro
        if isinstance(result, dict) and "error" in result:
            errors.append(result)
        else:
            results.append(result)

    return json.dumps(
        {
            "results": results,
            "errors": errors,
            "summary": {
                "total": len(urls),
                "success": len(results),
                "failed": len(errors),
            },
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Local file conversion
# ---------------------------------------------------------------------------


async def convert_local_files(paths: list[str]) -> str:
    """Convert local files to Markdown via markitdown.

    Args:
        paths: List of absolute file paths (max 10).

    Returns:
        JSON array of {path, content, title} or {path, error}.
    """
    if len(paths) > _MAX_CONVERT_FILES:
        return f"Error: Maximum {_MAX_CONVERT_FILES} files per call (got {len(paths)})"

    from wet_mcp.config import settings as _settings
    from wet_mcp.security import is_safe_local_path

    if _settings.convert_allowed_dirs:
        allowed_dirs = [
            Path(d.strip())
            for d in _settings.convert_allowed_dirs.split(",")
            if d.strip()
        ]
    else:
        # Default to allowing access only to the home directory and the
        # platform temp directory to prevent arbitrary file read of
        # sensitive system files. ``tempfile.gettempdir()`` returns the
        # OS-level temp dir (``/tmp`` on Linux, ``$TMPDIR`` /
        # ``/var/folders/...`` on macOS, ``C:\Users\<u>\AppData\Local\Temp``
        # on Windows) — hardcoding ``/tmp`` breaks on non-Linux hosts.
        allowed_dirs = [
            Path.home().resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]

    results = []
    for path_str in paths:
        safe_path = is_safe_local_path(
            path_str,
            allowed_dirs=allowed_dirs,
            max_size=_settings.convert_max_file_size,
        )
        if safe_path is None:
            results.append({"path": path_str, "error": f"Path rejected: {path_str}"})
            continue

        try:
            content = await asyncio.to_thread(_convert_file, safe_path)
            results.append(
                {
                    "path": str(safe_path),
                    "content": content,
                    "title": safe_path.name,
                }
            )
        except Exception as e:
            results.append({"path": path_str, "error": str(e)})

    return json.dumps(results, ensure_ascii=False, indent=2)


def _convert_file(path: Path) -> str:
    """Synchronous file conversion via markitdown."""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content
