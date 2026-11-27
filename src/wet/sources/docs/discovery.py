"""Documentation library discovery orchestrator and llms.txt probing."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from loguru import logger

from ._compat import pkg_attr
from ._http import _is_github_url, _safe_httpx_client
from .cleaning import _TOC_LINE_RE
from .probing import _is_readthedocs_host, _probe_docs_url
from .registries import (
    _GITHUB_LANGUAGE_NAMES,
    _LANGUAGE_REGISTRIES,
    _REGISTRY_FUNCTIONS,
    _discover_from_github_search,
    _get_github_homepage,
    _normalize_language,
)
from .well_known import _WELL_KNOWN_DOCS


def _score_discovery_result(r: dict, name: str) -> int:
    """Score a discovery result for relevance to the library name."""
    score = 0
    # Exact name match is the strongest signal
    if r.get("name", "").lower() == name.lower():
        score += 10
    # Has a docs/homepage URL
    homepage = r.get("homepage", "")
    if homepage:
        score += 5
        # Non-GitHub homepage = established project with custom domain
        parsed_hp = urlparse(homepage)
        if parsed_hp.netloc and not _is_github_url(homepage):
            lib_norm = name.lower().replace("-", "")
            if parsed_hp.netloc in ("docs.rs", "pkg.go.dev"):
                score += 1  # Auto-generated docs, minimal boost
                # Don't give name-in-path bonus: always true for these
            else:
                score += 3
                # Library name appears in the domain → likely official site
                # e.g. fastapi.tiangolo.com, pytorch.org, react.dev
                host_norm = parsed_hp.netloc.lower().replace("-", "")
                if lib_norm in host_norm:
                    score += 3
            # ReadTheDocs bonus: only when subdomain exactly matches lib name
            # Prevents e.g. "app-turbo.readthedocs.org" scoring for "turbo"
            if _is_readthedocs_host(parsed_hp.netloc):
                subdomain = parsed_hp.netloc.split(".")[0].lower().replace("-", "")
                if subdomain == lib_norm:
                    score += 2
    # Description quality (longer = more established)
    desc = r.get("description", "")
    if desc:
        desc_len = len(desc)
        if desc_len > 100:
            score += 3
        elif desc_len > 50:
            score += 2
        elif desc_len > 20:
            score += 1

    # Penalize deprecated packages (npm deprecate-holder, squatted names)
    if r.get("deprecated"):
        score -= 20

    # Penalize known placeholder/junk homepage patterns
    all_urls = ((homepage or "") + " " + (r.get("repository") or "")).lower()
    if any(p in all_urls for p in ("deprecate-holder", "placeholder")):
        score -= 15

    # Penalize crates.io auto-generated docs.rs fallback URLs
    if r.get("docs_rs_fallback"):
        score -= 2

    # Popularity boost for packages with star count data (Go, GitHub)
    # Helps disambiguate generic names like "echo", "gin", etc.
    stars = r.get("stars", 0)
    if stars >= 10000:
        score += 3
    elif stars >= 1000:
        score += 2
    elif stars >= 100:
        score += 1

    # Download count boost for crates.io packages
    # Helps disambiguate generic names: clap (668M), diesel (22M), etc.
    # Higher bonuses than stars because download counts are more reliable
    # for popularity (no manual curation needed).
    downloads = r.get("downloads", 0)
    if downloads >= 50_000_000:
        score += 5
    elif downloads >= 5_000_000:
        score += 3
    elif downloads >= 500_000:
        score += 1

    # Registry trust: npm/PyPI are direct package registries (exact API match),
    # while Go uses GitHub search (may return tangentially related repos).
    # Give primary registries a small bonus to break ties.
    reg = r.get("registry", "")
    if reg in ("npm", "pypi"):
        score += 2

    return score


async def _pre_upgrade_discovery_results(results: list[dict]) -> None:
    """Pre-upgrade results with GitHub homepages to their official homepages.

    This catches PyPI packages that only list their GitHub page as "homepage"
    (e.g. crawl4ai → crawl4ai.com).
    """
    upgrade_tasks = []
    upgrade_indices = []
    for i, r in enumerate(results):
        homepage = r.get("homepage") or ""
        repo_url = r.get("repository") or ""
        hp_is_github = _is_github_url(homepage)
        # Upgrade when NO homepage at all, OR homepage IS a GitHub URL
        if (not homepage or hp_is_github) and (repo_url or homepage):
            gh_url = repo_url if _is_github_url(repo_url) else homepage
            if _is_github_url(gh_url):
                upgrade_tasks.append(
                    pkg_attr("_get_github_homepage", _get_github_homepage)(gh_url)
                )
                upgrade_indices.append(i)

    if upgrade_tasks:
        gh_results = await asyncio.gather(*upgrade_tasks, return_exceptions=True)
        for idx, gh_hp in zip(upgrade_indices, gh_results, strict=False):
            if isinstance(gh_hp, str) and gh_hp:
                results[idx]["homepage"] = gh_hp
                logger.debug(
                    f"Pre-upgraded {results[idx].get('name')}"
                    f" homepage from GitHub: {gh_hp}"
                )


async def _finalize_discovery_result(best: dict, name: str, score: int) -> dict:
    """Perform final upgrades and probing on the best discovery result."""
    # GitHub homepage upgrade: when the homepage is a GitHub URL,
    # check the GitHub API for a better homepage (e.g. vuejs.org).
    homepage = best.get("homepage", "")
    repo_url = best.get("repository", "")
    if homepage and _is_github_url(homepage):
        # Try to extract owner/repo from either homepage or repo URL
        gh_url = repo_url if repo_url else homepage
        gh_homepage = await pkg_attr("_get_github_homepage", _get_github_homepage)(
            gh_url
        )
        if gh_homepage:
            logger.info(f"Upgraded {name} homepage: {homepage} -> {gh_homepage}")
            best["homepage"] = gh_homepage

    if best.get("homepage"):
        # Probe for better docs URL (docs subdomain, ReadTheDocs, /docs/)
        original_hp = best["homepage"]
        probed_url = await pkg_attr("_probe_docs_url", _probe_docs_url)(
            original_hp, name, registry=best.get("registry", "")
        )
        if probed_url != original_hp:
            logger.info(f"Upgraded {name} docs URL: {original_hp} -> {probed_url}")
            best["homepage"] = probed_url

        logger.info(
            f"Discovered {name} docs: {best['homepage']} "
            f"(via {best['registry']}, score={score})"
        )
    return best


async def _discover_via_github_search_with_upgrades(
    name: str, language: str
) -> dict | None:
    """Discover a library via GitHub search and perform upgrades/probing."""
    lang = _normalize_language(language)
    gh_result = await pkg_attr(
        "_discover_from_github_search", _discover_from_github_search
    )(name, lang)
    if not gh_result:
        return None

    # Probe for better docs URL
    homepage = gh_result.get("homepage", "")
    if homepage and not _is_github_url(homepage):
        probed = await pkg_attr("_probe_docs_url", _probe_docs_url)(
            homepage, name, registry="github"
        )
        if probed != homepage:
            logger.info(f"Probed {name} docs: {homepage} -> {probed}")
            gh_result["homepage"] = probed

    # Try to upgrade GitHub-only homepage via API
    repo_url = gh_result.get("repository", "")
    if homepage and _is_github_url(homepage) and repo_url:
        gh_hp = await pkg_attr("_get_github_homepage", _get_github_homepage)(repo_url)
        if gh_hp:
            logger.info(f"Upgraded {name} homepage: {homepage} -> {gh_hp}")
            gh_result["homepage"] = gh_hp

    return gh_result


async def discover_library(name: str, language: str | None = None) -> dict | None:
    """Discover library metadata from package registries.

    Queries all supported registries in parallel. Scores by:
    1. Exact name match (case-insensitive)
    2. Has valid docs/homepage URL
    3. Non-GitHub homepage (custom domain = established project)
    4. Description length (longer = more established)
    5. Dedicated docs URL pattern (readthedocs, docs.*, etc.)

    Supported registries:
    - npm (JavaScript/TypeScript)
    - PyPI (Python)
    - crates.io (Rust)
    - Go modules (Go)
    - Maven Central (Java/Kotlin/Scala)
    - Hex.pm (Elixir/Erlang)
    - Packagist (PHP)
    - pub.dev (Dart/Flutter)
    - RubyGems (Ruby)
    - NuGet (C#/.NET)

    When ``language`` is specified, only queries matching registries.
    """
    # Priority 0: Well-known docs
    well_known = _WELL_KNOWN_DOCS.get(name.lower())
    if well_known:
        logger.info(f"Using well-known docs for {name}: {well_known['homepage']}")
        return {**well_known, "name": name, "registry": "well_known"}

    # Build registry tasks based on language filter
    if language:
        lang = _normalize_language(language)
        registry_names = _LANGUAGE_REGISTRIES.get(lang)
        if registry_names is not None:
            if not registry_names:
                # Known language but no registry — try GitHub search
                logger.info(
                    f"No registry for language '{language}', "
                    "trying GitHub search fallback"
                )
                return await _discover_via_github_search_with_upgrades(name, language)
            # Query only matching registries
            tasks = [
                _REGISTRY_FUNCTIONS[r](name)
                for r in registry_names
                if r in _REGISTRY_FUNCTIONS
            ]
        else:
            # Unknown language — query all registries as fallback
            tasks = [f(name) for f in _REGISTRY_FUNCTIONS.values()]
    else:
        # No language specified — query all registries (default)
        tasks = [f(name) for f in _REGISTRY_FUNCTIONS.values()]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid_results = [r for r in results if isinstance(r, dict)]

    # Pre-upgrade results from GitHub API before scoring
    await _pre_upgrade_discovery_results(valid_results)

    # Score each result for relevance
    scored: list[tuple[int, dict]] = []
    for r in valid_results:
        score = _score_discovery_result(r, name)
        scored.append((score, r))

    # Sort by score descending, pick best
    scored.sort(key=lambda x: x[0], reverse=True)

    if scored:
        best_score, best = scored[0]
        return await _finalize_discovery_result(best, name, best_score)

    # All registries failed — try GitHub search as last resort
    if language:
        lang = _normalize_language(language)
        if lang in _GITHUB_LANGUAGE_NAMES:
            logger.info(
                f"All registries failed for {name} ({language}), "
                "trying GitHub search as last resort"
            )
            return await _discover_via_github_search_with_upgrades(name, language)

    return None


def _normalize_docs_url(url: str) -> str:
    """Normalize an overly-specific docs URL to a broader docs root.

    When a package registry returns a deeply nested page URL
    (e.g., ``/docs/stable/clients/python/overview``), normalize it to the
    docs root for better crawler coverage (e.g., ``/docs/stable/``).

    Only normalizes when there are 3+ path segments after a docs marker.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    parts = path.split("/")

    doc_markers = ("docs", "doc", "documentation")
    for i, p in enumerate(parts):
        if p.lower() in doc_markers:
            remaining = len(parts) - i - 1
            if remaining >= 3:
                keep_up_to = i + 2  # docs + one level (version/section)
                normalized_path = "/".join(parts[:keep_up_to]) + "/"
                normalized = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
                logger.info(f"Normalized docs URL: {url} -> {normalized}")
                return normalized
            break

    return url


# ---------------------------------------------------------------------------
# llms.txt discovery — try to fetch AI-friendly docs
# ---------------------------------------------------------------------------


async def try_llms_txt(base_url: str) -> str | None:
    """Try fetching llms-full.txt or llms.txt from a site.

    Returns content if found, None otherwise.
    """
    if not base_url:
        return None

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # Try both variants — prefer llms-full.txt (actual content)
    for filename in ("llms-full.txt", "llms.txt"):
        url = f"{origin}/{filename}"
        try:
            async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
                timeout=20, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    content = resp.text
                    # Validate: should be substantial text, not an error page
                    # Slicing the first 2000 characters before `lstrip` prevents
                    # allocating a massive copy of the entire body if leading
                    # whitespace is present, minimizing memory allocation overhead.
                    if len(content) > 200 and not content[:2000].lstrip().startswith(
                        "<!DOCTYPE"
                    ):
                        # llms.txt (non-full) is often just a TOC with links.
                        # Check quality: if >50% of non-empty lines are just
                        # markdown links, skip — better to crawl actual pages.
                        if filename == "llms.txt" and pkg_attr(
                            "_is_toc_only", _is_toc_only
                        )(content):
                            logger.info(
                                f"Skipping {url}: TOC-only content, "
                                "will fall back to crawling"
                            )
                            continue
                        logger.info(f"Found {filename} at {url} ({len(content)} chars)")
                        return content
        except Exception:
            continue

    return None


def _is_toc_only(content: str) -> bool:
    """Check if content is mostly a table of contents (links only).

    Returns True if >50% of non-empty lines are markdown links or bare URLs,
    indicating the file is just a TOC rather than actual documentation.
    """
    toc_lines = 0
    heading_lines = 0
    total_lines = 0

    for line in content.splitlines():
        if not line or line.isspace():
            continue

        total_lines += 1
        line = line.lstrip()

        if line.startswith("#"):
            heading_lines += 1
        elif _TOC_LINE_RE.match(line):
            toc_lines += 1

    if not total_lines:
        return True

    content_lines = total_lines - toc_lines - heading_lines
    # If less than 50% of lines are actual content, it's a TOC
    return content_lines < total_lines * 0.5
