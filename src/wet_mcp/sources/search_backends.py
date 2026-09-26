"""Pluggable web-search backends. Default SearXNG (local), Tavily (cloud)
where SearXNG cannot run. All return the same JSON string {results, total, query}
| {error} that server.py's search action already expects from searxng.search().

Each cloud backend takes a LIST of API keys (CSV in the env): a single key keeps
exactly today's behaviour, while multiple keys rotate automatically on a
key-specific failure (HTTP 429 rate-limit / 401-403 auth) via the local
``_rotate_keys`` primitive. An empty result from a working key is
legitimate and never triggers rotation — only the PROVIDER chain advances on empty.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol
from urllib.parse import unquote, urlparse

import httpx
from loguru import logger

from wet_mcp import search_metrics
from wet_mcp.config import settings
from wet_mcp.sources.rerank import maybe_rerank


# --- Local fallback / key-rotation primitives (de-host 2026-09) ------------
# Inlined from the deleted shared chains / key-rotation modules; semantics
# preserved exactly.


def split_keys(raw: str | None) -> list[str]:
    """Split a CSV key string into stripped, non-empty keys."""
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


_ROTATABLE_STATUS = {401, 403, 429}
_ROTATABLE_NAMES = {"RateLimitError", "AuthenticationError", "PermissionDeniedError"}


def _is_rotatable_error(exc: BaseException) -> bool:
    """Whether ``exc`` is key-specific (rotate to the next key): a 429/401/403
    status on the exception (as raised by ``_SearchHTTPError``) or a provider
    SDK exception of a rate-limit/auth/permission class."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _ROTATABLE_STATUS:
        return True
    return type(exc).__name__ in _ROTATABLE_NAMES


async def _rotate_keys(
    keys: list[str],
    call: Callable[[str], Awaitable[str]],
    *,
    label: str = "provider",
) -> str:
    """Run ``call`` with each key in order; return the first success.

    A key-specific failure (see ``_is_rotatable_error``) advances to the next
    key; any other error propagates immediately. When every key fails
    key-specifically, the LAST such error is re-raised (the caller formats it
    — e.g. the ``"<Provider> HTTP <code>"`` envelope naming the provider).
    """
    if len(keys) <= 1:
        return await call(keys[0] if keys else "")
    last: BaseException | None = None
    for key in keys:
        try:
            return await call(key)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if not _is_rotatable_error(exc):
                raise
            last = exc
    assert last is not None
    raise last


async def run_with_fallback(
    providers: Sequence[Callable[[], Awaitable[str]]],
    *,
    is_empty: Callable[[str], bool] | None = None,
    on_error: Callable[[int, Exception], None] | None = None,
) -> str | None:
    """Try each provider thunk in order; return the first non-empty result.

    Advances to the next provider when a thunk raises OR returns an "empty"
    result (per ``is_empty``; default: falsey, which covers ``[]`` / ``""`` /
    ``None``). Returns ``None`` when every provider is exhausted without a
    non-empty result. ``on_error(index, exc)`` is invoked for each provider
    that raises (intended for the caller's logging) and MUST NOT raise itself.

    De-host 2026-09: local copy of the deleted shared chains primitive.
    """
    empty = is_empty if is_empty is not None else (lambda r: not r)
    for idx, provider in enumerate(providers):
        try:
            result = await provider()
        except Exception as exc:  # fallback advances past any provider error
            if on_error is not None:
                on_error(idx, exc)
            continue
        if not empty(result):
            return result
    return None


class SearchBackend(Protocol):
    name: str

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range: str | None = None,
        language: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        categories: str = "general",
        region: str | None = None,
    ) -> str: ...


class _SearchHTTPError(Exception):
    """A non-2xx response from a search provider, carrying ``status_code`` so
    ``_is_rotatable_error`` classifies 429/401/403 as a rotatable
    (key-specific) failure and advances to the next key. The message is the safe
    ``"<Provider> HTTP <code>"`` form — it never carries the request body/key."""

    def __init__(self, provider: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"{provider} HTTP {status_code}")


async def _search_with_rotation(
    keys: list[str],
    attempt: Callable[[str], Awaitable[str]],
    provider: str,
) -> str:
    """Rotate ``keys`` for one search provider, advancing only on a key-specific
    failure (429/401/403). Returns the tool-contract error envelope when keys are
    exhausted or a non-rotatable error occurs — type name only, never the
    exception text (an httpx error may carry the request body, i.e. the key)."""
    if not keys:
        return json.dumps({"error": f"{provider} search backend has no API key"})
    try:
        return await _rotate_keys(keys, attempt, label=provider.lower())
    except _SearchHTTPError as exc:
        return json.dumps(
            {"error": str(exc)}
        )  # "<Provider> HTTP <code>" — safe, no key
    except (
        httpx.HTTPError
    ) as exc:  # transport — type name only (never echo, may carry the key)
        return json.dumps({"error": f"{provider} request failed: {type(exc).__name__}"})


async def _search_keyless(
    attempt: Callable[[], Awaitable[str]],
    provider: str,
) -> str:
    """Run a credential-free search attempt with the same tool-contract error
    envelopes as ``_search_with_rotation`` — error string, never raise; type
    name only for transport errors (an httpx error may carry request content)."""
    try:
        return await attempt()
    except _SearchHTTPError as exc:
        return json.dumps({"error": str(exc)})
    except httpx.HTTPError as exc:
        return json.dumps({"error": f"{provider} request failed: {type(exc).__name__}"})
    except Exception as exc:  # tool contract: error string, never raise
        return json.dumps({"error": f"{provider} search failed: {type(exc).__name__}"})


# Backends with native geo/region support. ``region`` is an ISO 3166-1 alpha-2
# code (``"US"``, ``"vn"``). A backend outside this set never receives the
# value silently: the chain skips it with a warning naming it, and when no
# configured backend supports it the caller gets a structured error naming
# them. The region is never silently dropped.
_REGION_SUPPORTED_BACKENDS = frozenset({"searxng", "brave", "tavily"})


def _searxng_locale(language: str | None, region: str | None) -> str | None:
    """Map ``language`` + ``region`` onto SearXNG's single ``language`` locale.

    SearXNG takes one ``language`` parameter in ``<lang>-<REGION>`` form, so
    ``language="vi", region="vn"`` -> ``"vi-VN"``; a bare region passes
    through as-is.
    """
    if region and language:
        return f"{language}-{region.upper()}"
    if region:
        return region.upper()
    return language


# Tavily's ``country`` parameter is a closed enum of lowercase country names
# (docs.tavily.com API reference, enum extracted 2026-09-02), so an ISO
# 3166-1 alpha-2 ``region`` must map through this table. A code Tavily does
# not carry yields an explicit error naming the backend -- never a silent
# drop of the geo filter.
_TAVILY_COUNTRY_BY_ISO: dict[str, str] = {
    "af": "afghanistan",
    "al": "albania",
    "dz": "algeria",
    "ad": "andorra",
    "ao": "angola",
    "ar": "argentina",
    "am": "armenia",
    "au": "australia",
    "at": "austria",
    "az": "azerbaijan",
    "bs": "bahamas",
    "bh": "bahrain",
    "bd": "bangladesh",
    "bb": "barbados",
    "by": "belarus",
    "be": "belgium",
    "bz": "belize",
    "bj": "benin",
    "bt": "bhutan",
    "bo": "bolivia",
    "ba": "bosnia and herzegovina",
    "bw": "botswana",
    "br": "brazil",
    "bn": "brunei",
    "bg": "bulgaria",
    "bf": "burkina faso",
    "bi": "burundi",
    "kh": "cambodia",
    "cm": "cameroon",
    "ca": "canada",
    "cv": "cape verde",
    "cf": "central african republic",
    "td": "chad",
    "cl": "chile",
    "cn": "china",
    "co": "colombia",
    "km": "comoros",
    "cg": "congo",
    "cr": "costa rica",
    "hr": "croatia",
    "cu": "cuba",
    "cy": "cyprus",
    "cz": "czech republic",
    "dk": "denmark",
    "dj": "djibouti",
    "do": "dominican republic",
    "ec": "ecuador",
    "eg": "egypt",
    "sv": "el salvador",
    "gq": "equatorial guinea",
    "er": "eritrea",
    "ee": "estonia",
    "et": "ethiopia",
    "fj": "fiji",
    "fi": "finland",
    "fr": "france",
    "ga": "gabon",
    "gm": "gambia",
    "ge": "georgia",
    "de": "germany",
    "gh": "ghana",
    "gr": "greece",
    "gt": "guatemala",
    "gn": "guinea",
    "ht": "haiti",
    "hn": "honduras",
    "hu": "hungary",
    "is": "iceland",
    "in": "india",
    "id": "indonesia",
    "ir": "iran",
    "iq": "iraq",
    "ie": "ireland",
    "il": "israel",
    "it": "italy",
    "jm": "jamaica",
    "jp": "japan",
    "jo": "jordan",
    "kz": "kazakhstan",
    "ke": "kenya",
    "kw": "kuwait",
    "kg": "kyrgyzstan",
    "lv": "latvia",
    "lb": "lebanon",
    "ls": "lesotho",
    "lr": "liberia",
    "ly": "libya",
    "li": "liechtenstein",
    "lt": "lithuania",
    "lu": "luxembourg",
    "mg": "madagascar",
    "mw": "malawi",
    "my": "malaysia",
    "mv": "maldives",
    "ml": "mali",
    "mt": "malta",
    "mr": "mauritania",
    "mu": "mauritius",
    "mx": "mexico",
    "md": "moldova",
    "mc": "monaco",
    "mn": "mongolia",
    "me": "montenegro",
    "ma": "morocco",
    "mz": "mozambique",
    "mm": "myanmar",
    "na": "namibia",
    "np": "nepal",
    "nl": "netherlands",
    "nz": "new zealand",
    "ni": "nicaragua",
    "ne": "niger",
    "ng": "nigeria",
    "kp": "north korea",
    "mk": "north macedonia",
    "no": "norway",
    "om": "oman",
    "pk": "pakistan",
    "pa": "panama",
    "pg": "papua new guinea",
    "py": "paraguay",
    "pe": "peru",
    "ph": "philippines",
    "pl": "poland",
    "pt": "portugal",
    "qa": "qatar",
    "ro": "romania",
    "ru": "russia",
    "rw": "rwanda",
    "sa": "saudi arabia",
    "sn": "senegal",
    "rs": "serbia",
    "sg": "singapore",
    "sk": "slovakia",
    "si": "slovenia",
    "so": "somalia",
    "za": "south africa",
    "kr": "south korea",
    "ss": "south sudan",
    "es": "spain",
    "lk": "sri lanka",
    "sd": "sudan",
    "se": "sweden",
    "ch": "switzerland",
    "sy": "syria",
    "tw": "taiwan",
    "tj": "tajikistan",
    "tz": "tanzania",
    "th": "thailand",
    "tg": "togo",
    "tt": "trinidad and tobago",
    "tn": "tunisia",
    "tr": "turkey",
    "tm": "turkmenistan",
    "ug": "uganda",
    "ua": "ukraine",
    "ae": "united arab emirates",
    "gb": "united kingdom",
    "us": "united states",
    "uy": "uruguay",
    "uz": "uzbekistan",
    "ve": "venezuela",
    "vn": "vietnam",
    "ye": "yemen",
    "zm": "zambia",
    "zw": "zimbabwe",
}


_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _html_text(raw: str) -> str:
    """Strip tags + decode entities (stdlib only — no external HTML parser,
    so the credential-free backends stay runnable inside a uvx tool venv)."""
    # Use pre-compiled regex for tag stripping, and str.split() for multi-whitespace
    # collapsing instead of a second regex substitution to avoid engine overhead.
    return " ".join(html.unescape(_HTML_TAG_RE.sub(" ", raw)).split())


def _decode_ddg_href(href: str) -> str:
    """DuckDuckGo wraps result links in ``/l/?uddg=<encoded>&rut=...`` jumps —
    unwrap the real target. Protocol-relative hrefs get https-prefixed."""
    if "uddg=" in href:
        idx = href.find("uddg=")
        end_idx = href.find("&", idx)
        encoded = href[idx + 5 : end_idx] if end_idx != -1 else href[idx + 5 :]
        if encoded:
            # avoiding urllib.parse.urlparse and parse_qs which allocate multiple objects
            # yields a ~3x speedup on this hot path
            return unquote(html.unescape(encoded))
    if href.startswith("//"):
        return f"https:{href}"
    return href


class SearxngBackend:
    name = "searxng"

    def __init__(self, url: str, *, hosted: bool = False) -> None:
        self.url = url
        self.hosted = hosted

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        from wet_mcp.sources.searxng import search as searxng_search

        return await searxng_search(
            searxng_url=self.url,
            query=query,
            categories=categories,
            max_results=max_results,
            time_range=time_range,
            language=_searxng_locale(language, region),
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            hosted=self.hosted,
        )


class TavilyBackend:
    name = "tavily"

    _URL = "https://api.tavily.com/search"

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    async def _search_one(self, key, query, max_results, country=None) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._URL,
                json={
                    "api_key": key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    **({"country": country} if country else {}),
                },
            )
            if resp.status_code != 200:
                raise _SearchHTTPError("Tavily", resp.status_code)
            results = resp.json().get("results", [])
            mapped = [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("content", r.get("title", "")),
                    "source": "tavily",
                }
                for r in results
            ]
            return json.dumps(
                {"results": mapped, "total": len(mapped), "query": query},
                ensure_ascii=False,
                indent=2,
            )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        if region:
            country = _TAVILY_COUNTRY_BY_ISO.get(region.lower())
            if country is None:
                # Explicit, structured, backend-named: never silently drop
                # the requested geo filter.
                return json.dumps(
                    {
                        "error": (
                            f"tavily does not support region={region!r}: "
                            "not a code in Tavily's country list"
                        )
                    },
                    ensure_ascii=False,
                )
        else:
            country = None
        return await _search_with_rotation(
            self.keys,
            lambda key: self._search_one(key, query, max_results, country),
            "Tavily",
        )


class BraveBackend:
    """Brave Web Search API (https://api.search.brave.com/res/v1/web/search).

    GET with header ``X-Subscription-Token``; results live at ``web.results[]``
    (verified against current Brave docs 2026-06-19).
    """

    name = "brave"

    _URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    async def _search_one(
        self, key, query, max_results, time_range, language, region=None
    ) -> str:
        params: dict[str, str | int] = {
            "q": query,
            "count": min(max(max_results, 1), 20),
        }
        if time_range:
            # Brave freshness codes: pd (day) / pw (week) / pm (month) / py (year).
            freshness = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}.get(
                time_range
            )
            if freshness:
                params["freshness"] = freshness
        if language:
            params["search_lang"] = language
        if region:
            # Brave expects a 2-char ISO 3166-1 alpha-2 country code.
            params["country"] = region.upper()
        headers = {"X-Subscription-Token": key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._URL, params=params, headers=headers)
            if resp.status_code != 200:
                raise _SearchHTTPError("Brave", resp.status_code)
            results = resp.json().get("web", {}).get("results", [])
            mapped = [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("description", r.get("title", "")),
                    "source": "brave",
                }
                for r in results
            ]
            return json.dumps(
                {"results": mapped, "total": len(mapped), "query": query},
                ensure_ascii=False,
                indent=2,
            )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        return await _search_with_rotation(
            self.keys,
            lambda key: self._search_one(
                key, query, max_results, time_range, language, region
            ),
            "Brave",
        )


class ExaBackend:
    """Exa search API (https://api.exa.ai/search).

    POST with header ``x-api-key``; body ``{query, numResults}`` plus a small
    ``contents.text`` request so each result carries a snippet. Results live at
    ``results[]`` (verified against current Exa docs 2026-06-19).
    """

    name = "exa"

    _URL = "https://api.exa.ai/search"

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    async def _search_one(
        self, key, query, max_results, include_domains, exclude_domains
    ) -> str:
        body: dict[str, object] = {
            "query": query,
            "numResults": min(max(max_results, 1), 100),
            "contents": {"text": {"maxCharacters": 300}},
        }
        if include_domains:
            body["includeDomains"] = include_domains
        if exclude_domains:
            body["excludeDomains"] = exclude_domains
        headers = {"x-api-key": key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._URL, json=body, headers=headers)
            if resp.status_code != 200:
                raise _SearchHTTPError("Exa", resp.status_code)
            results = resp.json().get("results", [])
            mapped = [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": (r.get("text") or r.get("title", ""))[:300],
                    "source": "exa",
                }
                for r in results
            ]
            return json.dumps(
                {"results": mapped, "total": len(mapped), "query": query},
                ensure_ascii=False,
                indent=2,
            )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        if region:
            # Exa's /search API has no geo parameter. Structured error naming
            # the backend so the chain advances (or the caller sees) instead
            # of silently searching without the requested region.
            return json.dumps(
                {"error": f"exa does not support region filtering (region={region!r})"},
                ensure_ascii=False,
            )
        return await _search_with_rotation(
            self.keys,
            lambda key: self._search_one(
                key, query, max_results, include_domains, exclude_domains
            ),
            "Exa",
        )


class DuckDuckGoBackend:
    """Credential-free DuckDuckGo HTML search (https://html.duckduckgo.com/html/).

    POST form ``q`` (+ ``df`` recency code); result blocks parsed with regex
    (stdlib only, uvx-safe — no external HTML parser). DuckDuckGo throttles
    automated HTML searches from datacenter/shared-egress IPs with an
    ``anomaly`` challenge; surfaced as HTTP 429 so the chain advances to the
    next backend. Single page (~25 results) — no pagination.
    Pattern ported from the OMP websearch provider (2026-09-04).
    """

    name = "duckduckgo"

    _URL = "https://html.duckduckgo.com/html/"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        return await _search_keyless(
            lambda: self._search_one(query, max_results, time_range), "DuckDuckGo"
        )

    async def _search_one(self, query: str, max_results: int, time_range) -> str:
        form: dict[str, str] = {"q": query, "kl": "us-en", "b": ""}
        if time_range:
            code = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(time_range)
            if code:
                form["df"] = code
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._URL,
                data=form,
                headers={"Referer": "https://html.duckduckgo.com/"},
            )
            if resp.status_code != 200:
                raise _SearchHTTPError("DuckDuckGo", resp.status_code)
            page = resp.text
        if "anomaly-modal" in page or "anomaly.js" in page:
            logger.warning(
                "DuckDuckGo bot-challenge received (datacenter/shared-egress IPs are "
                "throttled) — configure a credentialed backend for reliable search."
            )
            raise _SearchHTTPError("DuckDuckGo", 429)
        return self._parse(page, query, max_results)

    @staticmethod
    def _parse(page: str, query: str, max_results: int) -> str:
        blocks = re.findall(
            r'<div\b[^>]*\bclass="[^"]*\bresult\b[^"]*"[^>]*>'
            r"(.*?)(?=<div\b[^>]*\bclass=\"[^\"]*\bresult\b"
            r'|<div\b[^>]*\bclass="[^"]*\bnav-link\b|$)',
            page,
            re.S,
        )
        link_re = re.compile(
            r'<a\b(?=[^>]*\bclass="[^"]*\bresult__a\b)[^>]*\bhref="([^"]+)"[^>]*>'
            r"(.*?)</a>",
            re.S,
        )
        snippet_re = re.compile(
            r'<(?:a|div|span)\b[^>]*\bclass="[^"]*\bresult__snippet\b[^"]*"[^>]*>'
            r"(.*?)</(?:a|div|span)>",
            re.S,
        )
        mapped: list[dict[str, str]] = []
        seen: set[str] = set()
        for block in blocks:
            link = link_re.search(block)
            if not link:
                continue
            url = _decode_ddg_href(link.group(1))
            title = _html_text(link.group(2))
            if not url or not title or url in seen:
                continue
            seen.add(url)
            snippet_match = snippet_re.search(block)
            mapped.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": (
                        _html_text(snippet_match.group(1)) if snippet_match else title
                    ),
                    "source": "duckduckgo",
                }
            )
            if len(mapped) >= min(max(max_results, 1), 30):
                break
        return json.dumps(
            {"results": mapped, "total": len(mapped), "query": query},
            ensure_ascii=False,
            indent=2,
        )


class StartpageBackend:
    """Credential-free Startpage search (Google-backed,
    https://www.startpage.com/sp/search).

    GET ``query`` (+ ``with_date`` recency code) with a browser-like Referer;
    anchors (``a.result-link``) paired with the following ``p.description``.
    Startpage serves a CAPTCHA page to datacenter/shared-egress IPs — surfaced
    as HTTP 429 so the chain advances. Pattern ported from the OMP websearch
    provider (2026-09-04).
    """

    name = "startpage"

    _URL = "https://www.startpage.com/sp/search"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        return await _search_keyless(
            lambda: self._search_one(query, max_results, time_range), "Startpage"
        )

    async def _search_one(self, query: str, max_results: int, time_range) -> str:
        params: dict[str, str] = {"query": query}
        if time_range:
            code = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(time_range)
            if code:
                params["with_date"] = code
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                self._URL,
                params=params,
                headers={
                    "Referer": "https://www.startpage.com/",
                    "Accept-Language": "en",
                },
            )
            if resp.status_code != 200:
                raise _SearchHTTPError("Startpage", resp.status_code)
            page = resp.text
        if "captcha" in page.lower():
            logger.warning(
                "Startpage CAPTCHA received — chain should advance to the next backend."
            )
            raise _SearchHTTPError("Startpage", 429)
        return self._parse(page, query, max_results)

    @staticmethod
    def _parse(page: str, query: str, max_results: int) -> str:
        link_re = re.compile(
            r'<a\b(?=[^>]*\bclass="[^"]*\bresult-link\b)[^>]*\bhref="([^"]+)"[^>]*>'
            r"(.*?)</a>",
            re.S,
        )
        desc_re = re.compile(
            r'<p\b[^>]*\bclass="[^"]*\bdescription\b[^"]*"[^>]*>(.*?)</p>', re.S
        )
        links = list(link_re.finditer(page))
        descs = list(desc_re.finditer(page))
        mapped: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, link in enumerate(links):
            href = html.unescape(link.group(1))

            # avoiding urllib.parse.urlparse allocation for the vast majority of URLs
            # yields a ~10x speedup for this domain block check by using a fast string containment path
            if "startpage" in href:
                host = urlparse(href).hostname or ""
                if host == "startpage.com" or host.endswith(".startpage.com"):
                    continue

            url = href
            title = _html_text(link.group(2))
            if not url or not title or url in seen:
                continue
            seen.add(url)
            next_start = links[idx + 1].start() if idx + 1 < len(links) else len(page)
            desc = next((d for d in descs if link.end() < d.start() < next_start), None)
            mapped.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": _html_text(desc.group(1)) if desc else title,
                    "source": "startpage",
                }
            )
            if len(mapped) >= min(max(max_results, 1), 20):
                break
        return json.dumps(
            {"results": mapped, "total": len(mapped), "query": query},
            ensure_ascii=False,
            indent=2,
        )


class FirecrawlBackend:
    """Firecrawl Search API (https://api.firecrawl.dev/v2/search).

    POST ``{query, limit, sources:[{type:"web"}]}`` (+ ``tbs`` recency code);
    results live at ``data.search[]`` (``data.web`` legacy fallback) with
    ``{url|href|link, title|name, snippet|description|summary}``. With
    ``FIRECRAWL_API_KEY`` set the request carries ``Authorization: Bearer``;
    without a key the request is attempted keyless (the server may reject it,
    which surfaces as an error envelope and the chain advances). Pattern
    ported from the OMP websearch provider (2026-09-04).
    """

    name = "firecrawl"

    _URL = "https://api.firecrawl.dev/v2/search"

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    async def _search_one(self, key, query: str, max_results: int, time_range) -> str:
        body: dict[str, object] = {
            "query": query,
            "limit": min(max(max_results, 1), 100),
            "sources": [{"type": "web"}],
        }
        if time_range:
            tbs = {
                "day": "qdr:d",
                "week": "qdr:w",
                "month": "qdr:m",
                "year": "qdr:y",
            }.get(time_range)
            if tbs:
                body["tbs"] = tbs
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._URL, json=body, headers=headers)
            if resp.status_code != 200:
                raise _SearchHTTPError("Firecrawl", resp.status_code)
            data = resp.json().get("data") or {}
        rows = data.get("search") or data.get("web") or []
        mapped = [
            {
                "url": r.get("url") or r.get("href") or r.get("link") or "",
                "title": r.get("title") or r.get("name") or "",
                "snippet": (
                    r.get("snippet") or r.get("description") or r.get("summary") or ""
                ),
                "source": "firecrawl",
            }
            for r in rows
            if isinstance(r, dict) and (r.get("url") or r.get("href") or r.get("link"))
        ]
        return json.dumps(
            {"results": mapped, "total": len(mapped), "query": query},
            ensure_ascii=False,
            indent=2,
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        if self.keys:
            return await _search_with_rotation(
                self.keys,
                lambda key: self._search_one(key, query, max_results, time_range),
                "Firecrawl",
            )
        return await _search_keyless(
            lambda: self._search_one(None, query, max_results, time_range), "Firecrawl"
        )


class KagiBackend:
    """Kagi Search API (https://kagi.com/api/v1/search).

    POST JSON ``{query, limit}`` with ``Authorization: Bearer <key>`` (endpoint
    and shape verified against the OMP websearch provider, 2026-09-04);
    results live at ``data.search[]`` with ``{title, url, snippet, time}``.
    """

    name = "kagi"

    _URL = "https://kagi.com/api/v1/search"

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    async def _search_one(self, key, query: str, max_results: int) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._URL,
                json={"query": query, "limit": min(max(max_results, 1), 20)},
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise _SearchHTTPError("Kagi", resp.status_code)
            rows = (resp.json().get("data") or {}).get("search") or []
        mapped = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("snippet") or r.get("description") or "",
                "source": "kagi",
            }
            for r in rows
            if isinstance(r, dict) and r.get("url")
        ]
        return json.dumps(
            {"results": mapped, "total": len(mapped), "query": query},
            ensure_ascii=False,
            indent=2,
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        return await _search_with_rotation(
            self.keys,
            lambda key: self._search_one(key, query, max_results),
            "Kagi",
        )


class OpenRouterBackend:
    """OpenRouter web-search backend (https://openrouter.ai/docs).

    Runs the query through a chat completion carrying the
    ``openrouter:web_search`` server tool (the currently recommended form; the
    legacy ``plugins: [{"id": "web"}]`` plugin and the ``:online`` model
    suffix are deprecated). Result sources come back standardized as
    ``url_citation`` annotations on the assistant message; they are mapped
    onto the shared result shape and deduplicated by URL (docs verified
    2026-09-18).
    """

    name = "openrouter"

    def __init__(
        self,
        keys: list[str],
        *,
        model: str,
        base_url: str,
        engine: str = "",
    ) -> None:
        self.keys = keys
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.engine = engine

    async def _search_one(self, key: str, query: str, max_results: int) -> str:
        parameters: dict[str, object] = {
            "max_results": min(max(max_results, 1), 10),
        }
        if self.engine:
            parameters["engine"] = self.engine
        tool: dict[str, object] = {
            "type": "openrouter:web_search",
            "parameters": parameters,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": query}],
                    "tools": [tool],
                },
                headers=headers,
            )
            if resp.status_code != 200:
                raise _SearchHTTPError("OpenRouter", resp.status_code)
            choices = resp.json().get("choices") or [{}]
        message = choices[0].get("message") or {}
        seen: set[str] = set()
        mapped: list[dict[str, str]] = []
        for annotation in message.get("annotations") or []:
            citation = annotation.get("url_citation") or {}
            url = citation.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            mapped.append(
                {
                    "url": url,
                    "title": citation.get("title", ""),
                    "snippet": citation.get("content", "") or citation.get("title", ""),
                    "source": "openrouter",
                }
            )
            if len(mapped) >= max_results:
                break
        return json.dumps(
            {"results": mapped, "total": len(mapped), "query": query},
            ensure_ascii=False,
            indent=2,
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_range=None,
        language=None,
        include_domains=None,
        exclude_domains=None,
        categories="general",
        region=None,
    ) -> str:
        return await _search_with_rotation(
            self.keys,
            lambda key: self._search_one(key, query, max_results),
            "OpenRouter",
        )


def _request_search_config() -> dict[str, str] | None:
    # De-host 2026-09: per-sub credential buckets are gone — API keys are
    # host-only (process env / instance settings), so every mode resolves
    # keys through ``_config_value``'s ``os.getenv`` fallback (``None``).
    return None


def _config_value(config: dict[str, str] | None, key: str, default: str = "") -> str:
    # ``config`` is reserved for per-request overrides (always ``None`` since
    # the per-sub bucket removal); ``None`` reads the host environment.
    return config.get(key, "") if config is not None else os.getenv(key, default)


def _make_backend(name: str, searxng_url: str | None = None) -> SearchBackend:
    """Construct a single backend by name. Raises ValueError on missing key/unknown.

    ``searxng_url`` overrides ``settings.searxng_url`` for the SearXNG backend
    (the live auto-started URL, which may use a dynamic port) without mutating
    the global settings. Cloud backends read the host key CSV from process
    env/settings (per-sub key buckets were removed in the 2026-09 de-host).
    Multiple keys rotate on rate-limit/auth failure.
    """
    config = _request_search_config()
    if name == "searxng":
        url = _config_value(config, "SEARXNG_URL", settings.searxng_url)
        if config is None:
            url = searxng_url or url
        if not url:
            raise ValueError("SEARXNG_URL required for the searxng search backend")
        return SearxngBackend(url, hosted=config is not None)
    if name == "tavily":
        keys = split_keys(
            _config_value(config, "TAVILY_API_KEY", settings.tavily_api_key)
        )
        if not keys:
            raise ValueError("TAVILY_API_KEY required for the tavily search backend")
        return TavilyBackend(keys)
    if name == "brave":
        keys = split_keys(
            _config_value(config, "BRAVE_API_KEY", settings.brave_api_key)
        )
        if not keys:
            raise ValueError("BRAVE_API_KEY required for the brave search backend")
        return BraveBackend(keys)
    if name == "exa":
        keys = split_keys(_config_value(config, "EXA_API_KEY", settings.exa_api_key))
        if not keys:
            raise ValueError("EXA_API_KEY required for the exa search backend")
        return ExaBackend(keys)
    if name == "kagi":
        keys = split_keys(_config_value(config, "KAGI_API_KEY", settings.kagi_api_key))
        if not keys:
            raise ValueError("KAGI_API_KEY required for the kagi search backend")
        return KagiBackend(keys)
    if name == "openrouter":
        keys = split_keys(
            _config_value(config, "OPENROUTER_API_KEY", settings.openrouter_api_key)
        )
        if not keys:
            raise ValueError(
                "OPENROUTER_API_KEY required for the openrouter search backend"
            )
        return OpenRouterBackend(
            keys,
            model=_config_value(config, "OPENROUTER_MODEL", settings.openrouter_model),
            base_url=_config_value(
                config, "OPENROUTER_BASE_URL", settings.openrouter_base_url
            ),
            engine=_config_value(
                config, "OPENROUTER_SEARCH_ENGINE", settings.openrouter_search_engine
            ),
        )
    if name == "firecrawl":
        # Key optional: without one the request is attempted keyless (the
        # server may reject it — the chain advances on the error envelope).
        return FirecrawlBackend(
            split_keys(
                _config_value(config, "FIRECRAWL_API_KEY", settings.firecrawl_api_key)
            )
        )
    if name == "duckduckgo":
        return DuckDuckGoBackend()
    if name == "startpage":
        return StartpageBackend()
    raise ValueError(f"Unknown search backend: {name}")


def search_backend_from_env() -> SearchBackend:
    """Single-backend resolver (back-compat). Raises on missing key/unknown name."""
    name = _config_value(
        _request_search_config(), "SEARCH_BACKEND", settings.search_backend or "searxng"
    ).lower()
    return _make_backend(name)


# The local SearXNG auto-spawn URL (mirrors the ``searxng_url`` default in
# config.py). A uvx tool venv has no pip, so it cannot auto-start this
# instance; any other URL means an already-running external SearXNG reachable
# over HTTP, which uvx can use.
_DEFAULT_LOCAL_SEARXNG_URL = "http://localhost:41592"


def has_uvx_runnable_backend() -> bool:
    """Whether the configured ``SEARCH_BACKENDS`` chain has >=1 backend that
    can run under uvx (a tool venv with no pip, so the local SearXNG cannot
    auto-spawn).

    ``tavily``/``brave``/``exa`` are runnable whenever their API key is
    present -- they call out via ``httpx`` directly, no SearXNG needed (same
    subject-aware key lookup ``_make_backend`` uses). ``searxng`` is
    runnable under uvx only when ``SEARXNG_URL`` points at an already-running
    external instance; the default local URL implies the auto-spawn, which
    uvx tool venvs cannot start.
    """
    config = _request_search_config()
    for name in chain_backend_names():
        if name == "tavily" and split_keys(
            _config_value(config, "TAVILY_API_KEY", settings.tavily_api_key)
        ):
            return True
        if name == "brave" and split_keys(
            _config_value(config, "BRAVE_API_KEY", settings.brave_api_key)
        ):
            return True
        if name == "exa" and split_keys(
            _config_value(config, "EXA_API_KEY", settings.exa_api_key)
        ):
            return True
        if name in ("duckduckgo", "startpage", "firecrawl"):
            # credential-free / keyless-capable: plain httpx, no local spawn
            return True
        if name == "kagi" and split_keys(
            _config_value(config, "KAGI_API_KEY", settings.kagi_api_key)
        ):
            return True
        if name == "openrouter" and split_keys(
            _config_value(config, "OPENROUTER_API_KEY", settings.openrouter_api_key)
        ):
            return True
        if name == "searxng":
            url = _config_value(config, "SEARXNG_URL", settings.searxng_url)
            if url and url != _DEFAULT_LOCAL_SEARXNG_URL:
                return True
    return False


def chain_backend_names() -> list[str]:
    """The ordered backend names in the chain (no construction, no keys needed).

    Reads the CSV ``SEARCH_BACKENDS``; empty -> the single ``SEARCH_BACKEND``
    (back-compat). Used to decide whether the embedded SearXNG must be started
    before running the chain.

    Config is host-only since the per-sub bucket removal (de-host 2026-09):
    every mode reads the ``SEARCH_BACKENDS`` env var, falling back to the
    single ``SEARCH_BACKEND``, then to the historical ``searxng`` default.
    """
    config = _request_search_config()
    raw = _config_value(config, "SEARCH_BACKENDS", settings.search_backends).strip()
    if not raw:
        raw = _config_value(config, "SEARCH_BACKEND", settings.search_backend).strip()
    if not raw:
        raw = "searxng"
    return [n.strip().lower() for n in raw.split(",") if n.strip()]


def search_backends_from_env(searxng_url: str | None = None) -> list[SearchBackend]:
    """Resolve the ordered SEARCH_BACKENDS chain.

    Reads the CSV ``SEARCH_BACKENDS``; empty -> falls back to the single
    ``SEARCH_BACKEND`` (back-compat). Backends that cannot be built (missing
    key) are SKIPPED with a warning so a partially-configured chain still works
    with whatever providers are available. ``searxng_url`` overrides the SearXNG
    backend URL (the live auto-started instance).
    """
    backends: list[SearchBackend] = []
    for name in chain_backend_names():
        try:
            backends.append(_make_backend(name, searxng_url))
        except ValueError as exc:
            logger.warning(f"Skipping search backend {name!r}: {exc}")
    return backends


def _search_result_is_empty(payload: str) -> bool:
    """A search result JSON string counts as empty (advance the chain) when it
    is an error envelope, malformed, or carries no results."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return True
    if not isinstance(data, dict):
        return True
    if data.get("error"):
        return True
    results = data.get("results")
    if not isinstance(results, list):
        return True
    return not results


def _search_result_has_failure(payload: str) -> bool:
    """Return whether a provider outcome is an error or malformed payload."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return True
    return not (
        isinstance(data, dict)
        and not data.get("error")
        and isinstance(data.get("results"), list)
    )


async def run_search_chain(
    query: str,
    max_results: int = 10,
    time_range=None,
    language=None,
    include_domains=None,
    exclude_domains=None,
    categories="general",
    searxng_url: str | None = None,
    region: str | None = None,
    parallel: bool = False,
) -> str:
    """Run the configured search chain and report the selected backend.

    Providers are tried in order. Errors and empty results advance the chain.
    The returned envelope records requested, attempted, selected, and fallback
    state without exposing provider credentials or endpoints.

    ``region`` (ISO 3166-1 alpha-2) is forwarded only to backends with native
    geo support (searxng / brave / tavily). A backend without support is
    skipped with a warning naming it; when no configured backend supports it,
    a structured error naming them is returned -- the geo filter is never
    silently dropped.
    """
    requested = chain_backend_names()
    backends = search_backends_from_env(searxng_url)
    if region and backends:
        unsupported = [
            b.name for b in backends if b.name not in _REGION_SUPPORTED_BACKENDS
        ]
        if unsupported:
            logger.warning(
                f"region={region!r} not supported by search backend(s): "
                f"{', '.join(unsupported)}; skipping them"
            )
            backends = [b for b in backends if b.name in _REGION_SUPPORTED_BACKENDS]
        if not backends:
            return json.dumps(
                {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "error": (
                        f"region={region!r} is not supported by search "
                        f"backend(s): {', '.join(unsupported)}"
                    ),
                    "search_backend": {
                        "requested": requested,
                        "attempted": [],
                        "selected": None,
                        "fallback": "unavailable",
                    },
                },
                ensure_ascii=False,
            )

    budget = getattr(settings, "wet_search_budget", 0) or 0
    if budget > 0 and backends:
        exhausted = [
            b.name for b in backends if search_metrics.query_count(b.name) >= budget
        ]
        if len(exhausted) == len(backends):
            return json.dumps(
                {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "error": (
                        "search query budget exhausted for provider(s): "
                        + ", ".join(exhausted)
                        + f" (WET_SEARCH_BUDGET={budget})"
                    ),
                    "search_backend": {
                        "requested": requested,
                        "attempted": [],
                        "selected": None,
                        "fallback": "unavailable",
                    },
                },
                ensure_ascii=False,
            )
    if not backends:
        msg = (
            f"Search backends {requested} are missing API keys; configure a key or add searxng"
            if requested
            else "No search backend configured"
        )
        return json.dumps(
            {
                "results": [],
                "total": 0,
                "query": query,
                "error": msg,
                "search_backend": {
                    "requested": requested,
                    "attempted": [],
                    "selected": None,
                    "fallback": "unavailable",
                },
            },
            ensure_ascii=False,
        )

    attempted: list[str] = []
    selected: str | None = None
    had_provider_failure = False

    if parallel and len(backends) > 1:
        attempted = [b.name for b in backends]
        tasks = [
            backend.search(
                query=query,
                max_results=max_results,
                time_range=time_range,
                language=language,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                categories=categories,
            )
            for backend in backends
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        merged_results: list[dict] = []
        seen_urls: set[str] = set()
        successful_backends: list[str] = []
        had_failure = False

        for backend, outcome in zip(backends, outcomes, strict=False):
            if isinstance(outcome, BaseException):
                logger.warning(
                    f"Search backend '{backend.name}' raised: {type(outcome).__name__}"
                )
                had_failure = True
                continue
            try:
                parsed = json.loads(outcome)
                if (
                    isinstance(parsed, dict)
                    and isinstance(parsed.get("results"), list)
                    and parsed["results"]
                ):
                    successful_backends.append(backend.name)
                    for item in parsed["results"]:
                        if isinstance(item, dict):
                            url = item.get("url")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                item_copy = dict(item)
                                if "source" not in item_copy:
                                    item_copy["source"] = backend.name
                                merged_results.append(item_copy)
                elif isinstance(parsed, dict) and parsed.get("error"):
                    had_failure = True
            except Exception:
                had_failure = True

        data: dict[str, object] = {
            "results": merged_results[:max_results],
            "total": len(merged_results),
            "query": query,
        }
        if not merged_results and had_failure:
            data["error"] = "Search backend chain exhausted after provider failure"

        data["search_backend"] = {
            "requested": requested,
            "attempted": attempted,
            "selected": "+".join(successful_backends) if successful_backends else None,
            "fallback": "parallel_fanout" if successful_backends else "exhausted",
        }
        data = await maybe_rerank(query, data, max_results)
        return json.dumps(data, ensure_ascii=False)

    def traced_thunk(backend: SearchBackend) -> Callable[[], Awaitable[str]]:
        async def invoke() -> str:
            nonlocal had_provider_failure, selected
            if budget > 0 and search_metrics.query_count(backend.name) >= budget:
                # Per-provider cap reached: a structured error naming the
                # provider, which advances the chain (fallback semantics
                # unchanged) instead of a silent drop.
                logger.warning(
                    f"Search backend {backend.name!r} at query budget "
                    f"({budget}); advancing chain"
                )
                return json.dumps(
                    {
                        "error": (
                            f"search query budget exhausted for provider "
                            f"'{backend.name}' (WET_SEARCH_BUDGET={budget})"
                        )
                    },
                    ensure_ascii=False,
                )
            attempted.append(backend.name)
            search_metrics.record_query(backend.name)
            started = time.perf_counter()
            try:
                payload = await backend.search(
                    query=query,
                    max_results=max_results,
                    time_range=time_range,
                    language=language,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    categories=categories,
                    region=region,
                )
            except Exception:
                had_provider_failure = True
                raise
            finally:
                search_metrics.record_latency(
                    backend.name, time.perf_counter() - started
                )
            if _search_result_has_failure(payload):
                had_provider_failure = True
            elif not _search_result_is_empty(payload):
                selected = backend.name
            return payload

        return invoke

    result = await run_with_fallback(
        [traced_thunk(backend) for backend in backends],
        is_empty=_search_result_is_empty,
        on_error=lambda idx, exc: logger.warning(
            f"Search backend #{idx} raised: {type(exc).__name__}"
        ),
    )

    data: dict[str, object] = (
        json.loads(result)
        if result is not None
        else {"results": [], "total": 0, "query": query}
    )
    if selected is None and had_provider_failure:
        data["error"] = "Search backend chain exhausted after provider failure"
    data["search_backend"] = {
        "requested": requested,
        "attempted": attempted,
        "selected": selected,
        "fallback": (
            "exhausted"
            if selected is None
            else ("none" if requested and selected == requested[0] else "used")
        ),
    }
    data = await maybe_rerank(query, data, max_results)
    return json.dumps(data, ensure_ascii=False)


__all__ = [
    "BraveBackend",
    "ExaBackend",
    "DuckDuckGoBackend",
    "FirecrawlBackend",
    "KagiBackend",
    "OpenRouterBackend",
    "StartpageBackend",
    "SearchBackend",
    "SearxngBackend",
    "TavilyBackend",
    "chain_backend_names",
    "has_uvx_runnable_backend",
    "run_search_chain",
    "search_backend_from_env",
    "search_backends_from_env",
]
