"""Package registry and GitHub repository metadata discoverers."""

from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from ._compat import pkg_attr
from ._http import (
    _github_headers,
    _is_crates_url,
    _is_github_url,
    _safe_httpx_client,
)

# ---------------------------------------------------------------------------
# Registry discovery — find docs URL from library name
# ---------------------------------------------------------------------------


async def _discover_from_npm(name: str) -> dict | None:
    """Query npm registry for package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(f"https://registry.npmjs.org/{name}")
            if resp.status_code != 200:
                return None
            data = resp.json()

            # Detect deprecated packages (npm deprecate-holder, squatted names)
            is_deprecated = False
            dist_tags = data.get("dist-tags", {})
            latest_ver = dist_tags.get("latest", "")
            if latest_ver and isinstance(data.get("versions"), dict):
                ver_info = data["versions"].get(latest_ver, {})
                if ver_info.get("deprecated"):
                    is_deprecated = True

            repo_url = (
                data.get("repository", {}).get("url", "")
                if isinstance(data.get("repository"), dict)
                else (data.get("repository") or "")
            )
            # npm shorthand "owner/repo" → full GitHub URL
            if (
                repo_url
                and "/" in repo_url
                and "://" not in repo_url
                and not repo_url.startswith("git+")
            ):
                repo_url = f"https://github.com/{repo_url}"
            return {
                "name": data.get("name", name),
                "description": data.get("description", ""),
                "homepage": data.get("homepage") or "",
                "repository": repo_url,
                "registry": "npm",
                "deprecated": is_deprecated,
            }
    except Exception as e:
        logger.debug(f"npm lookup failed for {name}: {e}")
        return None


async def _discover_from_pypi(name: str) -> dict | None:
    """Query PyPI JSON API for package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(f"https://pypi.org/pypi/{name}/json")
            if resp.status_code != 200:
                return None
            data = resp.json()
            info = data.get("info", {})
            project_urls = info.get("project_urls") or {}
            # Case-insensitive project_urls lookup (PyPI has inconsistent casing)
            project_urls_lower = {k.lower(): v for k, v in project_urls.items() if v}
            docs_url = (
                project_urls_lower.get("documentation")
                or project_urls_lower.get("docs")
                or project_urls_lower.get("homepage")
                or info.get("docs_url")
                or info.get("home_page")
                or ""
            )
            repo_url = (
                project_urls_lower.get("repository")
                or project_urls_lower.get("source")
                or project_urls_lower.get("source code")
                or project_urls_lower.get("code")
                or ""
            )
            # Fallback: extract GitHub URL from any project_urls value
            # Many PyPI packages list GitHub under "Homepage", "Bug Tracker",
            # "Changelog", etc. without a dedicated "Repository" key.
            if not _is_github_url(repo_url):
                for _key, url_val in project_urls_lower.items():
                    if _is_github_url(url_val):
                        repo_url = url_val
                        break
            # Last resort: check top-level home_page field
            if not _is_github_url(repo_url):
                hp = info.get("home_page") or ""
                if _is_github_url(hp):
                    repo_url = hp
            return {
                "name": info.get("name", name),
                "description": info.get("summary") or "",
                "homepage": docs_url or info.get("home_page") or "",
                "repository": repo_url,
                "registry": "pypi",
            }
    except Exception as e:
        logger.debug(f"PyPI lookup failed for {name}: {e}")
        return None


async def _discover_from_crates(name: str) -> dict | None:
    """Query crates.io API for package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(
                f"https://crates.io/api/v1/crates/{name}",
                headers={"User-Agent": "wet/1.0"},
            )
            if resp.status_code != 200:
                return None
            crate = resp.json().get("crate", {})
            docs_url = crate.get("documentation") or ""
            hp_url = crate.get("homepage") or ""
            # Filter self-referencing crates.io URLs (listing page, not docs)
            if _is_crates_url(hp_url):
                hp_url = ""
            # Prefer homepage over docs.rs auto-generated documentation
            if hp_url:
                explicit_url = hp_url
            elif docs_url and "docs.rs" not in docs_url:
                explicit_url = docs_url
            else:
                explicit_url = ""
            # Use docs.rs fallback when no custom homepage/docs URL exists
            is_fallback = not explicit_url
            final_url = explicit_url or docs_url or f"https://docs.rs/{name}"
            return {
                "name": crate.get("name", name),
                "description": crate.get("description") or "",
                "homepage": final_url,
                "repository": crate.get("repository") or "",
                "registry": "crates",
                "docs_rs_fallback": is_fallback,
                "downloads": crate.get("downloads") or 0,
            }
    except Exception as e:
        logger.debug(f"crates.io lookup failed for {name}: {e}")
        return None


async def _discover_from_go(name: str) -> dict | None:
    """Query pkg.go.dev for Go module metadata.

    Searches pkg.go.dev for the package name and returns the top result.
    Falls back to GitHub API search for Go repositories if no direct match.
    This enables discovery of Go-only libraries like gin, echo, etc.
    """
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15, follow_redirects=True
        ) as client:
            # For Go packages with slash (e.g. "gorilla/mux"), search by
            # org or full name; for simple names, search by name alone.
            search_name = name.split("/")[-1] if "/" in name else name
            # Try GitHub search for Go repos with this name
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": f"{search_name} language:go",
                    "sort": "stars",
                    "per_page": 5,
                },
                headers=pkg_attr("_github_headers", _github_headers)(),
            )
            if resp.status_code != 200:
                return None
            items = resp.json().get("items", [])
            if not items:
                return None

            # Find the most relevant Go repo
            name_lower = name.lower()
            for item in items:
                repo_name = item.get("name", "").lower()
                full_name = item.get("full_name", "")
                full_name_lower = full_name.lower()
                # Match by repo name OR full_name for org/repo style
                name_match = False
                if "/" in name_lower:
                    # "gorilla/mux" should match full_name "gorilla/mux"
                    name_match = full_name_lower == name_lower
                else:
                    name_match = repo_name == name_lower
                if not name_match:
                    continue
                if item.get("language", "").lower() != "go":
                    continue
                # Require minimum popularity to avoid junk/clone repos
                stars = item.get("stargazers_count", 0)
                if stars < 50:
                    continue
                homepage = item.get("homepage") or ""
                description = item.get("description") or ""
                repo_url = item.get("html_url") or ""
                # Use homepage if it's a real docs domain (not github.com itself)
                if homepage and not _is_github_url(homepage):
                    docs_url = homepage
                else:
                    docs_url = f"https://pkg.go.dev/github.com/{full_name}"
                return {
                    "name": name,
                    "description": description,
                    "homepage": docs_url,
                    "repository": repo_url,
                    "registry": "go",
                    "stars": stars,
                }
    except Exception as e:
        logger.debug(f"Go module lookup failed for {name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Additional registry discovery functions
# ---------------------------------------------------------------------------


async def _discover_from_hex(name: str) -> dict | None:
    """Query Hex.pm API for Elixir/Erlang package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(
                f"https://hex.pm/api/packages/{name}",
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            meta = data.get("meta", {})
            links = meta.get("links", {})
            # Case-insensitive links lookup
            links_lower = {k.lower(): v for k, v in links.items() if v}
            docs_url = (
                data.get("docs_html_url")
                or links_lower.get("documentation")
                or links_lower.get("docs")
                or links_lower.get("homepage")
                or ""
            )
            repo_url = (
                links_lower.get("github")
                or links_lower.get("repository")
                or links_lower.get("source")
                or ""
            )
            # Fallback: hexdocs.pm is the standard Elixir docs host
            if not docs_url:
                docs_url = f"https://hexdocs.pm/{name}"
            return {
                "name": data.get("name", name),
                "description": meta.get("description") or "",
                "homepage": docs_url,
                "repository": repo_url,
                "registry": "hex",
                "downloads": data.get("downloads", {}).get("all", 0),
            }
    except Exception as e:
        logger.debug(f"Hex.pm lookup failed for {name}: {e}")
        return None


async def _discover_from_packagist(name: str) -> dict | None:
    """Query Packagist API for PHP package metadata.

    ``name`` can be either ``vendor/package`` (exact) or just ``package``
    (searches by keyword and picks the best match).
    """
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            if "/" in name:
                # Exact vendor/package lookup
                resp = await client.get(f"https://repo.packagist.org/p2/{name}.json")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                packages = data.get("packages", {}).get(name, [])
                if not packages:
                    return None
                latest = packages[0]  # First entry is latest
                return {
                    "name": name,
                    "description": latest.get("description") or "",
                    "homepage": latest.get("homepage") or "",
                    "repository": latest.get("source", {})
                    .get("url", "")
                    .replace("git+", "")
                    .replace(".git", ""),
                    "registry": "packagist",
                }
            else:
                # Search by keyword
                resp = await client.get(
                    "https://packagist.org/search.json",
                    params={"q": name, "per_page": 5},
                )
                if resp.status_code != 200:
                    return None
                results = resp.json().get("results", [])
                if not results:
                    return None
                # Prefer exact name match on package part
                name_lower = name.lower()
                best = None
                for r in results:
                    pkg_name = r.get("name", "")
                    pkg_part = (
                        pkg_name.split("/")[-1].lower()
                        if "/" in pkg_name
                        else pkg_name.lower()
                    )
                    if pkg_part == name_lower:
                        best = r
                        break
                if not best:
                    best = results[0]
                repo_url = best.get("repository") or ""
                return {
                    "name": best.get("name", name),
                    "description": best.get("description") or "",
                    "homepage": best.get("url") or "",
                    "repository": repo_url.replace(".git", ""),
                    "registry": "packagist",
                    "downloads": best.get("downloads", 0),
                }
    except Exception as e:
        logger.debug(f"Packagist lookup failed for {name}: {e}")
        return None


async def _discover_from_pubdev(name: str) -> dict | None:
    """Query pub.dev API for Dart/Flutter package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(f"https://pub.dev/api/packages/{name}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            latest = data.get("latest", {})
            pubspec = latest.get("pubspec", {})
            docs_url = pubspec.get("documentation") or pubspec.get("homepage") or ""
            repo_url = pubspec.get("repository") or ""
            # Fallback: pub.dev documentation page
            if not docs_url:
                docs_url = f"https://pub.dev/documentation/{name}/latest/"
            return {
                "name": pubspec.get("name", name),
                "description": pubspec.get("description") or "",
                "homepage": docs_url,
                "repository": repo_url,
                "registry": "pubdev",
            }
    except Exception as e:
        logger.debug(f"pub.dev lookup failed for {name}: {e}")
        return None


async def _discover_from_rubygems(name: str) -> dict | None:
    """Query RubyGems API for Ruby gem metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            resp = await client.get(f"https://rubygems.org/api/v1/gems/{name}.json")
            if resp.status_code != 200:
                return None
            data = resp.json()
            docs_url = data.get("documentation_uri") or data.get("homepage_uri") or ""
            repo_url = data.get("source_code_uri") or ""
            # Fallback: extract GitHub URL from any URI field
            if not _is_github_url(repo_url):
                for key in ("homepage_uri", "bug_tracker_uri", "changelog_uri"):
                    val = data.get(key) or ""
                    if _is_github_url(val):
                        repo_url = val
                        break
            return {
                "name": data.get("name", name),
                "description": data.get("info") or "",
                "homepage": docs_url,
                "repository": repo_url,
                "registry": "rubygems",
                "downloads": data.get("downloads", 0),
            }
    except Exception as e:
        logger.debug(f"RubyGems lookup failed for {name}: {e}")
        return None


async def _discover_from_nuget(name: str) -> dict | None:
    """Query NuGet API for .NET/C# package metadata."""
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            # NuGet service index → registration endpoint
            resp = await client.get(
                f"https://api.nuget.org/v3/registration5-gz-semver2/{name.lower()}/index.json",
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            # Get the latest catalog entry
            pages = data.get("items", [])
            if not pages:
                return None
            last_page = pages[-1]
            items = last_page.get("items")
            if not items:
                # Need to fetch the page
                page_url = last_page.get("@id")
                if page_url:
                    page_resp = await client.get(page_url)
                    if page_resp.status_code == 200:
                        items = page_resp.json().get("items", [])
            if not items:
                return None
            latest = items[-1].get("catalogEntry", {})
            project_url = latest.get("projectUrl") or ""
            repo_url = ""
            # Extract GitHub repo from project URL if available
            if _is_github_url(project_url):
                repo_url = project_url
            return {
                "name": latest.get("id", name),
                "description": latest.get("description") or "",
                "homepage": project_url,
                "repository": repo_url,
                "registry": "nuget",
            }
    except Exception as e:
        logger.debug(f"NuGet lookup failed for {name}: {e}")
        return None


async def _discover_from_maven(name: str) -> dict | None:
    """Query Maven Central for Java/Kotlin/Scala package metadata.

    ``name`` can be:
    - ``artifactId`` only (e.g. "guice") — searches all groups
    - ``groupId:artifactId`` (e.g. "com.google.inject:guice") — exact lookup
    """
    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=15
        ) as client:
            if ":" in name:
                group_id, artifact_id = name.split(":", 1)
                q = f'g:"{group_id}" AND a:"{artifact_id}"'
            else:
                q = f'a:"{name}"'
            resp = await client.get(
                "https://search.maven.org/solrsearch/select",
                params={"q": q, "rows": 5, "wt": "json"},
            )
            if resp.status_code != 200:
                return None
            docs = resp.json().get("response", {}).get("docs", [])
            if not docs:
                return None
            # Prefer exact artifactId match
            name_lower = name.split(":")[-1].lower() if ":" in name else name.lower()
            best = None
            for doc in docs:
                if doc.get("a", "").lower() == name_lower:
                    best = doc
                    break
            if not best:
                best = docs[0]
            group_id = best.get("g", "")
            artifact_id = best.get("a", "")
            # Build javadoc URL (standard Maven Central pattern)
            version = best.get("latestVersion") or best.get("v", "")
            homepage = ""
            if group_id and artifact_id and version:
                homepage = f"https://javadoc.io/doc/{group_id}/{artifact_id}/{version}"
            repo_url = ""
            # Try to find GitHub repo from scm info via additional API call
            if group_id and artifact_id and version:
                try:
                    pom_url = (
                        f"https://search.maven.org/solrsearch/select"
                        f"?q=g:{group_id}+AND+a:{artifact_id}+AND+v:{version}"
                        f"&rows=1&wt=json"
                    )
                    pom_resp = await client.get(pom_url)
                    if pom_resp.status_code == 200:
                        pom_docs = pom_resp.json().get("response", {}).get("docs", [])
                        if pom_docs:
                            # ec field contains extra info in some responses
                            pass
                except Exception:
                    pass
            return {
                "name": f"{group_id}:{artifact_id}" if group_id else name,
                "description": "",
                "homepage": homepage,
                "repository": repo_url,
                "registry": "maven",
            }
    except Exception as e:
        logger.debug(f"Maven Central lookup failed for {name}: {e}")
        return None


# Map canonical language names to GitHub language filters.
# GitHub uses specific casing/naming for its language: filter.
_GITHUB_LANGUAGE_NAMES: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "rust": "rust",
    "go": "go",
    "java": "java",
    "kotlin": "kotlin",
    "csharp": "c#",
    "php": "php",
    "ruby": "ruby",
    "swift": "swift",
    "c": "c",
    "cpp": "c++",
    "zig": "zig",
    "dart": "dart",
    "elixir": "elixir",
    "haskell": "haskell",
    "scala": "scala",
    "lua": "lua",
    "perl": "perl",
    "r": "r",
    "julia": "julia",
    "nim": "nim",
    "ocaml": "ocaml",
    "clojure": "clojure",
    "erlang": "erlang",
}


# Map of user-facing languages to acceptable GitHub primary languages.
# Many libraries have a primary GitHub language that differs from the
# language developers use to write code with them (e.g. nokogiri is a
# Ruby gem whose GitHub primary language is C because of native extensions).
_GITHUB_LANGUAGE_ACCEPT: dict[str, set[str]] = {
    "java": {"java", "groovy", "kotlin", "html", "javascript"},
    "kotlin": {"kotlin", "java"},
    "csharp": {"c#", "f#"},
    "php": {"php", "c", "c++"},
    "ruby": {"ruby", "c", "c++"},
    "swift": {"swift", "objective-c", "objective-c++", "c"},
    "lua": {"lua", "c", "c++", "objective-c", "moonscript"},
    "erlang": {"erlang", "elixir", "javascript"},
    "elixir": {"elixir", "erlang"},
    "dart": {"dart", "c++"},
    "cpp": {"c++", "c"},
    "c": {"c", "c++"},
    "rust": {"rust", "zig"},
    "go": {"go", "typescript", "javascript"},
    "scala": {"scala", "java"},
    "javascript": {"javascript", "typescript"},
    "typescript": {"typescript", "javascript"},
    "ocaml": {"ocaml", "reason"},
    "zig": {"zig", "c", "c++"},
    "haskell": {"haskell"},
    "nim": {"nim"},
    "clojure": {"clojure", "java"},
    "perl": {"perl"},
    "r": {"r"},
    "julia": {"julia"},
}


async def _discover_from_github_search(name: str, language: str) -> dict | None:
    """Search GitHub for a library repo by name and language.

    Generic fallback for languages without a dedicated package registry
    (Java, PHP, Ruby, Swift, Kotlin, C#, Dart, Elixir, etc.).

    Uses the GitHub search API sorted by stars.  Two passes:
      1. With ``language:{lang}`` filter — fast, targeted.
      2. Without the language filter — catches repos whose *primary*
         GitHub language differs from the user-facing language (e.g.
         nokogiri is Ruby but GitHub marks it as C).

    Language verification is relaxed: instead of requiring the primary
    language to match exactly, we accept members of the
    ``_GITHUB_LANGUAGE_ACCEPT`` set, and very popular repos (>=5 000
    stars) are accepted with no language check at all.
    """
    gh_lang = _GITHUB_LANGUAGE_NAMES.get(language)
    if not gh_lang:
        return None

    # For scoped names like "gorilla/mux", search the last part
    search_name = name.split("/")[-1] if "/" in name else name
    name_lower = name.lower()

    # Languages accepted for this user-facing language
    accept_langs = _GITHUB_LANGUAGE_ACCEPT.get(language, {gh_lang.lower()})

    async def _search_github(client: httpx.AsyncClient, query: str) -> list[dict]:
        """Execute a single GitHub search and return items."""
        try:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "per_page": 10,
                },
                headers=pkg_attr("_github_headers", _github_headers)(),
            )
            if resp.status_code != 200:
                logger.debug(f"GitHub search returned {resp.status_code} for q={query}")
                return []
            return resp.json().get("items", [])
        except Exception as e:
            logger.debug(f"GitHub search failed for q={query}: {e}")
            return []

    def _is_lang_ok(repo_lang: str, stars: int) -> bool:
        """Check if repository language is acceptable."""
        lang = repo_lang.lower()
        # Very popular repos are always accepted (>= 5000 stars)
        if stars >= 5000:
            return True
        # Otherwise, must be in the accept set
        return lang in accept_langs

    def _build_result(item: dict, match_type: str) -> dict:
        """Build a discovery result dict from a GitHub API item."""
        homepage = item.get("homepage") or ""
        repo_url = item.get("html_url") or ""
        stars = item.get("stargazers_count", 0)
        docs_url = homepage if (homepage and not _is_github_url(homepage)) else repo_url
        logger.info(
            f"GitHub search {match_type} {name} ({language}): "
            f"{repo_url} ({stars} stars)"
        )
        return {
            "name": name,
            "description": item.get("description") or "",
            "homepage": docs_url,
            "repository": repo_url,
            "registry": "github",
            "stars": stars,
        }

    # Build search queries:
    #   Pass 1: primary language filter  (e.g. ``language:elixir``)
    #   Pass 1b…: alt-language filters   (e.g. ``language:erlang`` for elixir)
    #   Pass 2: no language filter        (catches very popular mismatches)
    queries = [f"{search_name} language:{gh_lang}"]
    for alt in sorted(accept_langs):
        alt_gh = _GITHUB_LANGUAGE_NAMES.get(alt) or alt
        if alt_gh.lower() != gh_lang.lower():
            queries.append(f"{search_name} language:{alt_gh}")
    queries.append(search_name)

    async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
        timeout=15, follow_redirects=True
    ) as client:
        for query in queries:
            items = await _search_github(client, query)
            if not items:
                continue

            # Exact name match
            for item in items:
                repo_name = item.get("name", "").lower()
                full_name = item.get("full_name", "").lower()

                if "/" in name_lower:
                    name_match = full_name == name_lower
                else:
                    name_match = repo_name == name_lower

                if not name_match:
                    continue

                repo_lang = item.get("language") or ""
                stars = item.get("stargazers_count", 0)

                if not _is_lang_ok(repo_lang, stars):
                    continue
                if stars < 20:
                    continue

                return _build_result(item, "found")

            # Fuzzy match: name contained in repo name (top result only)
            top = items[0]
            top_name = top.get("name", "").lower()
            top_lang = top.get("language") or ""
            top_stars = top.get("stargazers_count", 0)

            if (
                _is_lang_ok(top_lang, top_stars)
                and top_stars >= 100
                and (
                    name_lower in top_name
                    or top_name in name_lower
                    or name_lower.replace("-", "") == top_name.replace("-", "")
                )
            ):
                return _build_result(top, "fuzzy match")

    return None


async def _get_github_homepage(url: str) -> str | None:
    """Fetch the GitHub repository's homepage URL via the API.

    When a package registry (npm) lists a GitHub URL as the homepage
    (e.g. ``github.com/vuejs/core/tree/main/packages/vue#readme``),
    the repo often has a dedicated docs site in its ``homepage`` field
    (e.g. ``https://vuejs.org/``).

    Returns the homepage URL if it's non-GitHub, else None.
    """
    # Extract owner/repo from various GitHub URL formats
    cleaned = url.replace("git+", "").replace(".git", "")
    m = re.search(r"github\.com[/:]([^/]+)/([^/#?]+)", cleaned)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)

    try:
        async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
            timeout=10, follow_redirects=True
        ) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=pkg_attr("_github_headers", _github_headers)(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            gh_homepage = data.get("homepage", "")
            if gh_homepage and not _is_github_url(gh_homepage):
                # Filter registry listing pages (uninformative, not docs)
                gh_lower = gh_homepage.lower()
                if any(
                    reg in gh_lower
                    for reg in (
                        "crates.io/crates/",
                        "pypi.org/project/",
                        "npmjs.com/package/",
                    )
                ):
                    return None
                return gh_homepage.rstrip("/")
    except Exception as e:
        logger.debug(f"GitHub homepage check failed for {owner}/{repo}: {e}")

    return None


# Language → registry mapping for targeted discovery
# ---------------------------------------------------------------------------

_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "node": "javascript",
    "nodejs": "javascript",
    "rs": "rust",
    "golang": "go",
    "kt": "kotlin",
    "c#": "csharp",
    "dotnet": "csharp",
    ".net": "csharp",
    "c++": "cpp",
    "rb": "ruby",
}

# Map normalized language to supported registries.
# Empty list = language known but no registry integration (use GitHub search).
_LANGUAGE_REGISTRIES: dict[str, list[str]] = {
    "python": ["pypi"],
    "javascript": ["npm"],
    "typescript": ["npm"],
    "rust": ["crates"],
    "go": ["go"],
    "java": ["maven"],
    "kotlin": ["maven"],
    "scala": ["maven"],
    "csharp": ["nuget"],
    "php": ["packagist"],
    "ruby": ["rubygems"],
    "dart": ["pubdev"],
    "elixir": ["hex"],
    "erlang": ["hex"],
    # Languages without integrated registry — use GitHub search fallback
    "swift": [],
    "c": [],
    "cpp": [],
    "zig": [],
    "haskell": [],
    "lua": [],
    "perl": [],
    "r": [],
    "julia": [],
    "clojure": [],
    "nim": [],
    "ocaml": [],
}

# Registry name → discovery function
_REGISTRY_FUNCTIONS: dict[str, Any] = {
    "npm": _discover_from_npm,
    "pypi": _discover_from_pypi,
    "crates": _discover_from_crates,
    "go": _discover_from_go,
    "hex": _discover_from_hex,
    "packagist": _discover_from_packagist,
    "pubdev": _discover_from_pubdev,
    "rubygems": _discover_from_rubygems,
    "nuget": _discover_from_nuget,
    "maven": _discover_from_maven,
}


def _normalize_language(language: str) -> str:
    """Normalize language name to canonical form."""
    lang = language.strip().lower()
    return _LANGUAGE_ALIASES.get(lang, lang)
