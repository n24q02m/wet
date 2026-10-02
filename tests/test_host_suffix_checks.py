"""Registry host checks must match the host suffix, not a URL substring.

CodeQL raised ``py/incomplete-url-substring-sanitization`` on the
``github_url=`` sink in ``_index_library_docs``, but the substring test it
flagged was the same one every registry discovery helper used. The values
being tested are publisher-controlled: ``repository`` / ``projectUrl`` /
``source_code_uri`` come straight out of npm, PyPI, crates.io, RubyGems and
NuGet metadata, so anyone who can publish a package can choose them.

``"github.com" in url`` accepts two shapes it should not:

* ``https://evil.example/?x=github.com`` -- the needle sits in the query.
* ``https://github.com.evil.example/a/b`` -- the needle is a *prefix* of an
  attacker-owned parent domain.

Neither is cosmetic. ``server.py`` promotes a "GitHub" repo URL straight into
``docs_url`` when discovery found no docs URL, so the crawler then fetches it;
the rest store it as the library's trusted ``github_url``.

The tests below drive the real discovery helpers with mocked registry
responses, so they fail on the substring implementation and pass on the
host-suffix one. ``test_legitimate_*`` pins the shapes that must keep working
-- notably bare ``github.com/o/r`` and ``git+https://github.com/o/r.git``,
which the substring check accepted and packages in the wild still publish.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.docs import (
    _discover_from_crates,
    _discover_from_nuget,
    _discover_from_pypi,
    _discover_from_rubygems,
    _is_crates_url,
    _is_github_url,
    _url_host,
)

# URLs an attacker can publish that a substring check wrongly accepts.
HOSTILE_URLS = [
    "https://evil.example/?x=github.com",
    "https://github.com.evil.example/a/b",
    "https://notgithub.com/a/b",
    "https://evil.example/github.com/a/b",
    "https://evil.example#github.com",
]

# URLs that really are GitHub and must survive the tightening.
LEGITIMATE_URLS = [
    "https://github.com/psf/requests",
    "git+https://github.com/psf/requests.git",
    "https://www.github.com/psf/requests",
    "http://github.com/psf/requests",
    "github.com/psf/requests",
]


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_is_github_url_rejects_hostile(url):
    assert _is_github_url(url) is False


@pytest.mark.parametrize("url", LEGITIMATE_URLS)
def test_is_github_url_accepts_legitimate(url):
    assert _is_github_url(url) is True


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("", ""),
        ("https://github.com/o/r", "github.com"),
        ("git+https://github.com/o/r.git", "github.com"),
        ("git@github.com:o/r.git", "github.com"),
        ("github.com/o/r", "github.com"),
        ("https://GitHub.COM/o/r", "github.com"),
        ("https://github.com.:443/o/r", "github.com"),
        ("https://user:pw@github.com/o/r", "github.com"),
        ("https://github.com.evil.example/o/r", "github.com.evil.example"),
    ],
)
def test_url_host_shapes(url, expected):
    assert _url_host(url) == expected


def test_is_crates_url_distinguishes_lookalikes():
    assert _is_crates_url("https://crates.io/crates/serde") is True
    assert _is_crates_url("https://crates.io.evil.example/x") is False
    assert _is_crates_url("https://evil.example/?ref=crates.io") is False


def _client(route_map):
    """Mock ``safe_httpx_client`` routing GETs by URL substring."""
    client = AsyncMock()
    missing = MagicMock()
    missing.status_code = 404

    async def _get(url, **kwargs):
        for key, resp in route_map.items():
            if key in str(url):
                return resp
        return missing

    client.get = AsyncMock(side_effect=_get)
    client.head = AsyncMock(side_effect=_get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _json_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _pypi_payload(url):
    # No "repository"/"source" key, so the helper falls back to scanning every
    # project_urls value -- the path that decides whether `url` becomes the repo.
    return {
        "info": {
            "name": "victim",
            "summary": "",
            "project_urls": {"Homepage": url},
            "home_page": "",
            "docs_url": "",
        }
    }


def _rubygems_payload(url):
    return {
        "name": "victim",
        "info": "",
        "documentation_uri": "",
        "homepage_uri": url,
        "source_code_uri": "",
        "downloads": 1,
    }


def _nuget_payload(url):
    return {
        "items": [
            {
                "items": [
                    {
                        "catalogEntry": {
                            "id": "victim",
                            "description": "",
                            "projectUrl": url,
                        }
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize("url", HOSTILE_URLS)
async def test_pypi_rejects_non_github_host(url):
    client = _client({"pypi.org": _json_response(_pypi_payload(url))})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_pypi("victim")
    assert result is not None
    assert result["repository"] != url


@pytest.mark.parametrize("url", HOSTILE_URLS)
async def test_rubygems_rejects_non_github_host(url):
    client = _client({"rubygems.org": _json_response(_rubygems_payload(url))})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_rubygems("victim")
    assert result is not None
    assert result["repository"] != url


@pytest.mark.parametrize("url", HOSTILE_URLS)
async def test_nuget_rejects_non_github_host(url):
    client = _client({"api.nuget.org": _json_response(_nuget_payload(url))})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_nuget("victim")
    assert result is not None
    assert result["repository"] != url


@pytest.mark.parametrize("url", LEGITIMATE_URLS)
async def test_legitimate_github_urls_still_accepted(url):
    client = _client({"pypi.org": _json_response(_pypi_payload(url))})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_pypi("victim")
    assert result is not None
    assert result["repository"] == url


async def test_crates_keeps_homepage_on_lookalike_host():
    """``crates.io.evil.example`` is not crates.io, so it is not self-referencing.

    The filter drops a homepage that merely points back at the crate's own
    listing page. A substring match also drops an unrelated third-party
    homepage whose URL happens to mention crates.io, losing real docs.
    """
    payload = {
        "crate": {
            "name": "victim",
            "description": "",
            "documentation": "",
            "homepage": "https://evil.example/?ref=crates.io",
            "repository": "",
            "downloads": 1,
        }
    }
    client = _client({"crates.io/api": _json_response(payload)})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_crates("victim")
    assert result is not None
    assert result["homepage"] == "https://evil.example/?ref=crates.io"


async def test_crates_still_drops_real_self_reference():
    payload = {
        "crate": {
            "name": "victim",
            "description": "",
            "documentation": "https://docs.rs/victim",
            "homepage": "https://crates.io/crates/victim",
            "repository": "",
            "downloads": 1,
        }
    }
    client = _client({"crates.io/api": _json_response(payload)})
    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=client):
        result = await _discover_from_crates("victim")
    assert result is not None
    assert result["homepage"] != "https://crates.io/crates/victim"
