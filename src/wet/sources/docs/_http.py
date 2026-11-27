"""Shared HTTP client, version constant, and URL host helpers for docs discovery."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from wet.security import safe_httpx_client as _safe_httpx_client  # noqa: F401

# Bump this whenever discovery scoring or crawl logic changes.
# Libraries cached with an older version are automatically re-indexed.
DISCOVERY_VERSION = 27


def _github_headers() -> dict[str, str]:
    """Return GitHub API headers, including auth token if available."""
    headers: dict[str, str] = {}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _apply_version_to_url(url: str, version: str | None) -> str:
    """Apply version to docs URL if applicable.

    Handles ReadTheDocs (/en/latest/ -> /en/{version}/) and
    docs.rs (/latest/ -> /{version}/) patterns.
    """
    if not version:
        return url
    # ReadTheDocs
    if "readthedocs" in url:
        url = re.sub(r"/en/(latest|stable)/", f"/en/{version}/", url)
    # docs.rs
    elif "docs.rs" in url:
        url = re.sub(r"/latest/", f"/{version}/", url)
    return url


def _url_host(url: str | None) -> str:
    """Lowercase host of a registry-supplied URL, or "" when there is none.

    The value is whatever a package publisher typed into npm / PyPI / crates.io
    / RubyGems / NuGet metadata, so one field arrives in several shapes:
    "https://github.com/o/r", "git+https://github.com/o/r.git",
    "git@github.com:o/r.git" and a bare "github.com/o/r". ``urlparse`` only
    fills ``netloc`` when a scheme is present, so the last two land entirely in
    ``path``; recover the host from ``path`` rather than reporting "no host",
    which would drop URLs the substring checks being replaced accepted and
    packages in the wild still publish.
    """
    if not url:
        return ""
    url = url.strip()

    # Performance Optimization: urlparse() is slow and allocates objects.
    # In hot paths, we manually slice standard HTTP(S) and git+https URLs
    # for a ~20% speedup. We fallback to urlparse for auth/IPv6/edge cases.
    if url.startswith(("http://", "https://", "git+https://")):
        start = url.find("://") + 3

        end1 = url.find("?", start)
        end2 = url.find("#", start)
        end3 = url.find("/", start)

        end = len(url)
        if end1 != -1 and end1 < end:
            end = end1
        if end2 != -1 and end2 < end:
            end = end2
        if end3 != -1 and end3 < end:
            end = end3

        if url.find("@", start, end) == -1 and url.find("[", start, end) == -1:
            netloc = url[start:end]
            host = netloc.partition(":")[0]
            return host.lower().rstrip(".")

    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    netloc = parsed.netloc or parsed.path.partition("/")[0]
    host = netloc.rpartition("@")[2]  # drop any userinfo
    host = host.partition(":")[0]  # drop the port, or the scp-style path
    return host.lower().rstrip(".")


def _is_github_url(url: str | None) -> bool:
    """True when url points at github.com or a host GitHub owns beneath it.

    The registry discovery helpers used to ask ``"github.com" in url``, which
    also accepts "https://evil.example/?x=github.com" (needle in the query) and
    "https://github.com.evil.example/a/b" (needle is the first label of someone
    else's domain) -- CodeQL's ``py/incomplete-url-substring-sanitization``.
    That mattered because a repo URL clearing this gate is stored as the
    library's trusted ``github_url`` and, when discovery found no docs URL, is
    promoted to ``docs_url`` and then fetched.

    Subdomains stay eligible: every host under github.com is GitHub's, so
    allowing them does not widen the trust boundary the way a substring does,
    and "www.github.com" is a spelling real metadata uses.
    """
    host = _url_host(url)
    return host == "github.com" or host.endswith(".github.com")


def _is_crates_url(url: str | None) -> bool:
    """True when url points at crates.io or a subdomain of it.

    Used to drop a homepage that only points back at the crate's own listing
    page. A substring match also drops an unrelated homepage that merely
    mentions crates.io in a query string, losing docs that do exist.
    """
    host = _url_host(url)
    return host == "crates.io" or host.endswith(".crates.io")
