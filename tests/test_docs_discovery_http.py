"""Discovery fallbacks of ``wet.sources.docs`` against an in-memory HTTP server.

The SSRF-guarded client factory (``_safe_httpx_client``) is swapped for a real
``httpx.AsyncClient`` on an ``httpx.MockTransport``, so the code under test
runs its own request/response handling; only the network is replaced.
"""

from __future__ import annotations

import zlib
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest

from wet.sources import docs

Handler = Callable[[httpx.Request], httpx.Response]


def _serve(handler: Handler):
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return patch.object(docs, "_safe_httpx_client", factory)


def _down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


# ---------------------------------------------------------------------------
# URL scoring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://d.io/guide/install#top",
        "https://d.io/guide/install?x=1",
        "https://d.io/guide/install?x=1#top",
        "https://d.io/guide/install#top?x=1",
        "https://user@d.io/guide/install?x=1",
    ],
)
def test_score_counts_path_words_only(url):
    """Only the path is scored: words in the query string or fragment never
    count, whichever of ``?`` / ``#`` comes first (and for URLs that take the
    ``urlparse`` route)."""
    assert docs._score_url_by_query(url, frozenset({"install", "guide"})) == 2
    assert docs._score_url_by_query(url, frozenset({"x", "top"})) == 0


def test_score_of_a_bare_origin_is_zero():
    assert docs._score_url_by_query("https://d.io", frozenset({"d", "io"})) == 0


# ---------------------------------------------------------------------------
# GitHub raw markdown tier
# ---------------------------------------------------------------------------

_API = "https://api.github.com/repos/acme/kit"
_RAW = "https://raw.githubusercontent.com/acme/kit/main"
_BODY = "# Title\n\n" + "Useful documentation text. " * 5


async def test_github_raw_docs_unreachable_api_falls_through():
    with _serve(_down):
        assert await docs._try_github_raw_docs("https://github.com/acme/kit") is None


async def test_github_raw_docs_without_a_tree_falls_through():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _API:
            return httpx.Response(200, json={"default_branch": "main"})
        return httpx.Response(404)

    with _serve(handler):
        assert await docs._try_github_raw_docs("https://github.com/acme/kit") is None


async def test_github_raw_docs_malformed_tree_falls_through():
    """A tree entry that is not an object is a malformed API answer: the
    tier gives up instead of raising into the docs pipeline."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _API:
            return httpx.Response(200, json={"default_branch": "main"})
        return httpx.Response(200, json={"tree": ["docs/a.md"]})

    with _serve(handler):
        assert await docs._try_github_raw_docs("https://github.com/acme/kit") is None


async def test_github_raw_docs_keep_only_files_that_fetch_cleanly():
    """Directories are not fetched; a 404, a stub file and a transport error
    each drop just that file, the rest become pages."""
    raw = {
        "docs/a.md": httpx.Response(200, text=_BODY),
        "docs/b.md": httpx.Response(404),
        "docs/c.md": httpx.Response(200, text="stub"),
        "docs/e.md": httpx.Response(200, text=_BODY),
        "docs/f.md": httpx.Response(200, text=_BODY),
    }
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == _API:
            return httpx.Response(200, json={"default_branch": "main"})
        if url.startswith(f"{_API}/git/trees/main"):
            tree = [{"type": "tree", "path": "docs"}]
            tree += [{"type": "blob", "path": p} for p in [*raw, "docs/d.md"]]
            return httpx.Response(200, json={"tree": tree})
        path = url.removeprefix(f"{_RAW}/")
        fetched.append(path)
        if path == "docs/d.md":
            raise httpx.ReadTimeout("slow", request=request)
        return raw[path]

    with _serve(handler):
        pages = await docs._try_github_raw_docs("https://github.com/acme/kit")

    assert pages is not None
    assert "docs" not in fetched
    assert sorted(fetched) == [f"docs/{name}.md" for name in "abcdef"]
    assert sorted(p["url"] for p in pages) == [
        "https://github.com/acme/kit/blob/main/docs/a.md",
        "https://github.com/acme/kit/blob/main/docs/e.md",
        "https://github.com/acme/kit/blob/main/docs/f.md",
    ]


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------


def _urlset(*locs: str) -> str:
    entries = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return f'<?xml version="1.0"?><urlset>{entries}</urlset>'


async def test_sitemap_index_survives_a_failing_sub_sitemap():
    """An HTML answer at /sitemap.xml is ignored; the index at
    /sitemap_index.xml is followed, a sub-sitemap that errors is skipped, and
    off-domain or non-doc URLs are filtered out."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/sitemap.xml":
            return httpx.Response(200, text="<html>not a sitemap</html>")
        if path == "/sitemap_index.xml":
            return httpx.Response(
                200,
                text=(
                    "<sitemapindex>"
                    "<sitemap><loc>https://docs.test/pages.xml</loc></sitemap>"
                    "<sitemap><loc>https://docs.test/broken.xml</loc></sitemap>"
                    "</sitemapindex>"
                ),
            )
        if path == "/pages.xml":
            return httpx.Response(
                200,
                text=_urlset(
                    "https://docs.test/guide/start",
                    "https://docs.test/blog/launch",
                    "https://elsewhere.test/guide/start",
                ),
            )
        raise httpx.ConnectError("reset", request=request)

    with _serve(handler):
        urls = await docs._try_sitemap("https://docs.test/guide/")

    assert urls == ["https://docs.test/guide/start"]


async def test_sitemap_with_no_doc_urls_yields_nothing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return httpx.Response(404)
        return httpx.Response(200, text=_urlset("https://docs.test/blog/post"))

    with _serve(handler):
        assert await docs._try_sitemap("https://docs.test/") == []


async def test_sitemap_unreachable_host_yields_nothing():
    with _serve(_down):
        assert await docs._try_sitemap("https://docs.test/") == []


# ---------------------------------------------------------------------------
# Sphinx objects.inv
# ---------------------------------------------------------------------------

_INV_HEADER = (
    b"# Sphinx inventory version 2\n# Project: kit\n# Version: 1\n"
    b"# The remainder of this file is compressed using zlib.\n"
)


async def test_objects_inv_candidates_that_fail_are_skipped():
    """Base URL unreachable (the given URL is used as-is), an inventory with
    no entries, a transport error and a 404 are each skipped in turn."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if url == "https://docs.test/api/objects.inv":
            return httpx.Response(200, content=_INV_HEADER + zlib.compress(b""))
        if url == "https://docs.test/api/stable/objects.inv":
            return httpx.Response(404)
        raise httpx.ConnectError("refused", request=request)

    with _serve(handler):
        assert await docs._try_objects_inv("https://docs.test/api") == []

    assert seen == [
        "https://docs.test/api",
        "https://docs.test/api/objects.inv",
        "https://docs.test/api/latest/objects.inv",
        "https://docs.test/api/stable/objects.inv",
    ]


async def test_objects_inv_ignores_non_sphinx_answers():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("objects.inv"):
            return httpx.Response(200, content=b"<html>soft 404</html>")
        return httpx.Response(200, text="ok")

    with _serve(handler):
        assert await docs._try_objects_inv("https://docs.test/") == []


# ---------------------------------------------------------------------------
# Registry-less discovery through GitHub search
# ---------------------------------------------------------------------------


async def test_github_search_matches_scoped_names_on_full_name():
    """A failing search query is skipped; a scoped name must equal the repo
    full name, and a matching repo below 20 stars is not trusted."""
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        queries.append(query)
        if query == "kit language:java":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {"name": "kit", "full_name": "other/kit", "stargazers_count": 900},
                    {"name": "kit", "full_name": "acme/kit", "stargazers_count": 3},
                ]
                if query != "kit"
                else [
                    {
                        "name": "kit",
                        "full_name": "acme/kit",
                        "language": "Java",
                        "stargazers_count": 40,
                        "html_url": "https://github.com/acme/kit",
                        "homepage": "https://kit.dev",
                    }
                ]
            },
        )

    with _serve(handler):
        found = await docs._discover_from_github_search("acme/kit", "java")

    assert found is not None
    assert queries[0] == "kit language:java"
    assert queries[-1] == "kit"
    assert found["repository"] == "https://github.com/acme/kit"
    assert found["homepage"] == "https://kit.dev"
    assert found["stars"] == 40


@pytest.mark.parametrize("stars,bonus", [(0, 0), (150, 1), (1500, 2), (25000, 3)])
def test_discovery_score_popularity_bonus_is_tiered(stars, bonus):
    base = {"name": "kit", "homepage": "", "stars": 0}
    assert (
        docs._score_discovery_result({**base, "stars": stars}, "kit")
        - docs._score_discovery_result(base, "kit")
        == bonus
    )


async def test_finalize_upgrades_a_github_homepage_to_the_project_site():
    """When the best result only points at GitHub, the repo's own homepage
    field (a non-GitHub site) replaces it."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://api.github.com/repos/acme/kit":
            return httpx.Response(200, json={"homepage": "https://kit.dev"})
        return httpx.Response(404)

    best = {
        "name": "kit",
        "homepage": "https://github.com/acme/kit#readme",
        "repository": "",
        "registry": "npm",
    }
    with _serve(handler):
        out = await docs._finalize_discovery_result(best, "kit", 15)

    assert out["homepage"] == "https://kit.dev"
