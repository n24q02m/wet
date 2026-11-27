"""Documentation URL probing and ReadTheDocs detection."""

from __future__ import annotations

import asyncio
import re
import zlib
from urllib.parse import urlparse

import httpx
from loguru import logger

from ._compat import pkg_attr
from ._http import _safe_httpx_client

# Generic package names that collide with unrelated RTD projects
_GENERIC_NAMES = frozenset(
    {
        "core",
        "react",
        "cli",
        "common",
        "utils",
        "types",
        "client",
        "server",
        "api",
        "app",
        "config",
        "test",
        "ui",
        "web",
    }
)

# Domains to skip for docs. subdomain probing (host-level docs, not project docs)
_SKIP_DOCS_SUBDOMAIN = {
    "github.com",
    "github.io",
    "gitlab.com",
    "bitbucket.org",
    "pypi.org",
    "npmjs.com",
    "npmjs.org",
    "crates.io",
}

# Registries where ReadTheDocs is unlikely/rare
_RTD_SKIP_REGISTRIES = {"npm", "crates", "go"}

# Path segments that indicate login/auth pages (false positive redirects)
_AUTH_SEGMENTS = (
    "/login",
    "/signin",
    "/signup",
    "/account",
    "/auth",
    "/register",
)
_AUTH_SEGMENTS_RE = re.compile("|".join(re.escape(seg) for seg in _AUTH_SEGMENTS))


def _get_doc_candidates(
    homepage: str, lib_name: str, registry: str
) -> list[tuple[str, str]]:
    """Generate potential documentation URLs for a library."""
    parsed = urlparse(homepage)
    netloc = parsed.netloc
    base_domain = netloc.removeprefix("www.") if netloc.startswith("www.") else netloc

    # Normalize lib name for probing
    scope_part = ""
    pkg_part = lib_name.lower().lstrip("@")
    if "/" in pkg_part:
        scope_part = pkg_part.split("/")[0]
        pkg_part = pkg_part.split("/")[-1]
    clean_name = pkg_part

    candidates: list[tuple[str, str]] = [("original", homepage)]

    # 1. docs.{domain} subdomain
    if not base_domain.startswith("docs.") and base_domain not in _SKIP_DOCS_SUBDOMAIN:
        candidates.append(("docs_subdomain", f"https://docs.{base_domain}/"))

    # 2. ReadTheDocs
    if (
        "readthedocs" not in base_domain
        and clean_name not in _GENERIC_NAMES
        and registry not in _RTD_SKIP_REGISTRIES
    ):
        rtd_name = scope_part or clean_name
        if len(rtd_name) > 4:
            candidates.append(
                ("readthedocs", f"https://{rtd_name}.readthedocs.io/en/latest/")
            )

    # 3. {homepage}/docs/ path
    if len(parsed.path.strip("/")) <= 1:
        docs_path_url = f"{parsed.scheme}://{parsed.netloc}/docs/"
        candidates.append(("docs_path", docs_path_url))

    return candidates


def _validate_rtd_inventory(
    inv_content: bytes, lib_name: str, clean_name_norm: str
) -> bool:
    """Validate ReadTheDocs objects.inv matches the library name and has content."""
    inv_text = inv_content[:500].decode("utf-8", errors="replace")
    proj_match = re.search(r"^# Project:\s*(.+)$", inv_text, re.MULTILINE)
    if proj_match:
        proj_name = (
            proj_match.group(1)
            .strip()
            .lower()
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if clean_name_norm not in proj_name:
            logger.debug(
                f"RTD project '{proj_match.group(1).strip()}' doesn't match '{lib_name}', skipping"
            )
            return False

    # Count objects: real docs have 50+, squatters < 30
    try:
        hdr_pos = 0
        for _ in range(4):
            hdr_pos = inv_content.index(b"\n", hdr_pos) + 1
        decompressed = zlib.decompress(inv_content[hdr_pos:])
        obj_count = len(decompressed.split(b"\n")) - 1
        if obj_count < 50:
            logger.debug(
                f"RTD {lib_name}: only {obj_count} objects, likely squatter — skipping"
            )
            return False
    except Exception:
        return False
    return True


async def _check_doc_candidate(
    client: httpx.AsyncClient,
    label: str,
    url: str,
    lib_name: str,
    clean_name_norm: str,
    original_netloc: str,
) -> tuple[str, str, int, bool] | None:
    """Probe and validate a single documentation candidate URL."""
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        content = resp.text
        content_len = len(content)
        if content_len < 500:
            return None

        final_url = str(resp.url)
        final_parsed = urlparse(final_url)
        final_path = final_parsed.path.lower()

        if _AUTH_SEGMENTS_RE.search(final_path):
            return None

        if final_parsed.netloc == original_netloc and label not in (
            "docs_path",
            "original",
        ):
            if not final_path.startswith("/docs") and "docs" not in final_parsed.netloc:
                return None

        has_inv = False
        inv_url = final_url.rstrip("/") + "/objects.inv"
        try:
            inv_resp = await client.get(inv_url)
            if inv_resp.status_code == 200 and inv_resp.content[:30].startswith(
                b"# Sphinx inventory version"
            ):
                if label == "readthedocs":
                    if not _validate_rtd_inventory(
                        inv_resp.content, lib_name, clean_name_norm
                    ):
                        return None
                has_inv = True
        except Exception:
            pass

        if label == "readthedocs" and not has_inv:
            return None

        return (label, final_url, content_len, has_inv)
    except Exception:
        return None


def _score_doc_candidate(label: str, size: int, has_inv: bool) -> int:
    """Calculate a quality score for a validated documentation URL."""
    score = 0
    if has_inv:
        score += 100  # Sphinx docs = gold standard
    if size > 10000:
        score += 10
    elif size > 2000:
        score += 5
    elif size > 500:
        score += 2

    if label == "docs_subdomain":
        score += 3
    if label == "original":
        score += 5
    return score


async def _probe_docs_url(homepage: str, lib_name: str, registry: str = "") -> str:
    """Probe for a better documentation URL than the project homepage.

    Many libraries list their marketing/landing page in package registries,
    but actual documentation lives at a different URL:

    - ``docs.{domain}`` subdomain (e.g., docs.solidjs.com, docs.nestjs.com)
    - ``{name}.readthedocs.io`` (validated via ``objects.inv`` project name)
    - ``{homepage}/docs/`` path (e.g., remix.run/docs/)

    Probes these alternatives in parallel. Returns the best URL found,
    preferring URLs with Sphinx ``objects.inv`` (guaranteed rich docs).
    Falls back to ``homepage`` if no better alternative exists.

    ReadTheDocs results are validated by parsing the ``objects.inv`` header
    project name — must match the library name to prevent false positives
    (e.g., ``chi.readthedocs.io`` being an unrelated Python project).
    """
    original_netloc = urlparse(homepage).netloc
    clean_name_norm = (
        lib_name.lower().lstrip("@").split("/")[-1].replace("-", "").replace("_", "")
    )

    candidates = _get_doc_candidates(homepage, lib_name, registry)
    if not candidates:
        return homepage

    async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
        timeout=10, follow_redirects=True
    ) as client:
        results = await asyncio.gather(
            *[
                _check_doc_candidate(
                    client, label, url, lib_name, clean_name_norm, original_netloc
                )
                for label, url in candidates
            ],
            return_exceptions=True,
        )

    valid = [r for r in results if isinstance(r, tuple) and r is not None]
    if not valid:
        return homepage

    # Pick best: objects.inv > large content > small content
    best: tuple[str, str] | None = None
    best_score = 0
    for label, final_url, size, has_inv in valid:
        score = _score_doc_candidate(label, size, has_inv)
        if score > best_score:
            best_score = score
            best = (label, final_url)

    if best:
        logger.info(
            f"Probed better docs URL for {lib_name}: {best[1]} "
            f"(via {best[0]}, score={best_score})"
        )
        return best[1]

    return homepage


_READTHEDOCS_HOSTS = (
    "readthedocs.io",
    "readthedocs.org",
    "rtfd.io",
    # Projects on ReadTheDocs for Business are served from this host instead;
    # the substring check this replaces matched them, so keep them eligible.
    "readthedocs-hosted.com",
)

# Optimization: O(1) exact match check using frozenset
_READTHEDOCS_HOSTS_SET = frozenset(_READTHEDOCS_HOSTS)
# Optimization: C-optimized suffix check using tuple passed to str.endswith
_READTHEDOCS_SUFFIXES = tuple(f".{h}" for h in _READTHEDOCS_HOSTS)


def _is_readthedocs_host(netloc: str) -> bool:
    """True when netloc is a ReadTheDocs host or a subdomain of one.

    Matching on the host suffix rather than a substring: "readthedocs" appearing
    anywhere in the netloc also matches an attacker-controlled parent domain such
    as "turbo.readthedocs.evil.com", whose first label would then pass the
    subdomain check below and collect the bonus.
    """
    host = netloc.lower().partition(":")[0].rstrip(".")
    # Optimization: Replaced Python generator expression with C-optimized checks
    # yielding a ~7x speedup by avoiding Python-level loop overhead.
    return host in _READTHEDOCS_HOSTS_SET or host.endswith(_READTHEDOCS_SUFFIXES)
