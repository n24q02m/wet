"""GitHub raw docs/README fallback and URL/path filtering helpers."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from loguru import logger

from ._compat import pkg_attr
from ._http import _github_headers, _safe_httpx_client
from .chunking import chunk_markdown
from .rst import _rst_to_markdown

# ---------------------------------------------------------------------------
# GitHub raw markdown — fetch docs directly from repo
# ---------------------------------------------------------------------------

# Pattern to extract owner/repo from GitHub URLs
_GH_REPO_RE = re.compile(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/|$)")

# Common docs directory names in repos.
# Defined as a frozenset to enable fast O(1) membership and intersection lookups via .isdisjoint().
_DOC_DIRS = frozenset(("docs", "doc", "documentation", "guide", "guides", "wiki"))

# Non-documentation files to skip (case-insensitive stem matching)
_SKIP_FILES = frozenset(
    {
        "changelog",
        "changes",
        "history",
        "contributing",
        "contributors",
        "code_of_conduct",
        "code-of-conduct",
        "license",
        "licence",
        "security",
        "release",
        "releases",
        "release-notes",
        "release_notes",
        "authors",
        "funding",
        "sponsors",
        "support",
        "codeowners",
        "pull_request_template",
        "issue_template",
        "bug_report",
        "feature_request",
    }
)

# ISO 639-1 language codes commonly used for i18n docs directories
_I18N_LANG_CODES = frozenset(
    {
        "af",
        "am",
        "ar",
        "az",
        "be",
        "bg",
        "bn",
        "bs",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "eo",
        "es",
        "et",
        "eu",
        "fa",
        "fi",
        "fr",
        "ga",
        "gl",
        "gu",
        "ha",
        "he",
        "hi",
        "hr",
        "hu",
        "hy",
        "id",
        "is",
        "it",
        "ja",
        "ka",
        "kk",
        "km",
        "kn",
        "ko",
        "ku",
        "ky",
        "lo",
        "lt",
        "lv",
        "mk",
        "ml",
        "mn",
        "mr",
        "ms",
        "my",
        "nb",
        "ne",
        "nl",
        "nn",
        "no",
        "pa",
        "pl",
        "ps",
        "pt",
        "ro",
        "ru",
        "si",
        "sk",
        "sl",
        "sq",
        "sr",
        "sv",
        "sw",
        "ta",
        "te",
        "th",
        "tl",
        "tr",
        "uk",
        "ur",
        "uz",
        "vi",
        "zh",
        # Common regional variants
        "pt-br",
        "zh-cn",
        "zh-tw",
        "zh-hans",
        "zh-hant",
    }
)

# Template/macro pattern (Jinja2, mkdocs-macros, etc.)
_TEMPLATE_MACRO_RE = re.compile(r"\{\{.*?\}\}")

_FRAMEWORK_DIR_RE = re.compile(r"(?:^|/)framework/(\w+)/")

# Frameworks commonly used in monorepo docs with framework/* subdirectories
_KNOWN_FRAMEWORKS = frozenset(
    {"react", "angular", "vue", "svelte", "solid", "qwik", "lit", "preact"}
)


def _filter_framework_paths(paths: list[str], library_hint: str) -> list[str]:
    """Filter docs paths to matching framework variant in monorepo docs.

    Detects patterns like ``docs/framework/react/...`` vs
    ``docs/framework/angular/...`` and keeps only the one matching
    the library name (e.g., ``@tanstack/react-query`` -> keep ``react``).
    """
    framework_paths: dict[str, list[str]] = {}
    non_framework_paths: list[str] = []

    for p in paths:
        match = _FRAMEWORK_DIR_RE.search(p.lower())
        if match and match.group(1) in _KNOWN_FRAMEWORKS:
            fw = match.group(1)
            framework_paths.setdefault(fw, []).append(p)
        else:
            non_framework_paths.append(p)

    if len(framework_paths) < 2:
        return paths

    # Extract framework hint from library name
    # e.g., "@tanstack/react-query" -> "react", "vue-router" -> "vue"
    hint_parts = library_hint.lower().replace("@", "").replace("/", "-").split("-")
    matching_fw = None
    for part in hint_parts:
        if part in framework_paths:
            matching_fw = part
            break

    if matching_fw:
        logger.info(
            f"Framework filter: keeping '{matching_fw}' docs "
            f"({len(framework_paths[matching_fw])} files), "
            f"skipping {', '.join(f for f in framework_paths if f != matching_fw)}"
        )
        return non_framework_paths + framework_paths[matching_fw]

    return paths


def _filter_doc_paths(
    md_paths: list[str], library_hint: str = ""
) -> tuple[list[str], bool]:
    """Smart filtering of markdown file paths from a GitHub repository tree.

    Handles three key problems:
    1. i18n directories — only keeps English or language-neutral docs
    2. Deeply nested docs — prefers top-level docs/ over packages/*/docs/
    3. README deprioritization — moves README.md to end of list

    Args:
        md_paths: List of file paths from GitHub tree API.

    Returns:
        Tuple of (filtered paths, has_primary_docs). ``has_primary_docs`` is
        True when the repo has a top-level ``docs/`` or similar directory,
        indicating the raw markdown is likely user-facing documentation
        rather than internal/tooling docs.
    """
    if not md_paths:
        return [], False

    # Separate README from docs
    readme_paths: list[str] = []
    doc_paths: list[str] = []
    for p in md_paths:
        if p.rsplit("/", 1)[-1].lower() in (
            "readme.md",
            "readme.mdx",
            "readme.rst",
        ):
            readme_paths.append(p)
        else:
            doc_paths.append(p)

    # --- Step 1: Detect and filter i18n structure ---
    # Look for sibling directories that are ISO 639-1 codes
    # e.g. docs/en/, docs/de/, docs/ja/ → keep only docs/en/
    i18n_filtered = _filter_i18n_paths(doc_paths)

    # --- Step 2: Prioritize top-level docs over deeply nested ---
    primary: list[str] = []  # docs/file.md, doc/guide/file.md
    nested: list[str] = []  # packages/foo/docs/file.md

    for p in i18n_filtered:
        parts = p.split("/")
        # Check if the FIRST segment is a doc directory
        if parts and parts[0].lower() in _DOC_DIRS:
            primary.append(p)
        else:
            nested.append(p)

    has_primary = len(primary) >= 5

    # Use nested docs only if primary docs has <5 files
    if has_primary:
        result = primary
    else:
        result = primary + nested

    # --- Step 3: Append README(s) at end (lowest priority) ---
    # Only include root README, not every sub-package README
    root_readmes = [p for p in readme_paths if "/" not in p]
    result.extend(root_readmes)

    # --- Step 4: Framework-specific filtering ---
    if library_hint:
        result = _filter_framework_paths(result, library_hint)

    return result, has_primary


def _filter_i18n_paths(paths: list[str]) -> list[str]:
    """Filter out non-English i18n documentation paths.

    Detects i18n structure by finding sibling directories under a common
    parent that match ISO 639-1 language codes. When i18n is detected,
    keeps only English (``en``) paths and language-neutral paths.

    Handles common patterns:
    - ``docs/en/...``, ``docs/de/...`` (direct lang subdirs)
    - ``docs/i18n/en/...``, ``docs/i18n/de/...`` (i18n subdir)
    - ``i18n/en/...``, ``i18n/de/...`` (top-level i18n)
    """
    if not paths:
        return paths

    # Group paths by their first two segments to detect i18n siblings
    # e.g. "docs/de/tutorial.md" → parent="docs", child_dir="de"
    parent_children: dict[str, set[str]] = {}
    for p in paths:
        parts = p.split("/")
        if len(parts) >= 3:
            parent = parts[0]
            child = parts[1].lower()
            parent_children.setdefault(parent, set()).add(child)

    # Find parents that have ≥2 children matching language codes
    i18n_parents: set[str] = set()
    for parent, children in parent_children.items():
        lang_codes = children & _I18N_LANG_CODES
        if len(lang_codes) >= 2:
            i18n_parents.add(parent)

    if not i18n_parents:
        return paths

    # Filter: for i18n parents, only keep English or language-neutral paths
    filtered: list[str] = []
    for p in paths:
        parts = p.split("/")
        if len(parts) >= 3 and parts[0] in i18n_parents:
            child = parts[1].lower()
            if child in _I18N_LANG_CODES:
                # Language directory — only keep English
                if child == "en":
                    filtered.append(p)
                # else: skip non-English translation
            else:
                # Not a language dir (e.g. docs/api/, docs/guide/) — keep
                filtered.append(p)
        else:
            # Path not under an i18n parent — keep
            filtered.append(p)

    logger.info(
        f"i18n filter: {len(paths)} paths → {len(filtered)} "
        f"(skipped translations under: {', '.join(sorted(i18n_parents))})"
    )
    return filtered


def _has_excessive_macros(content: str, threshold: float = 0.15) -> bool:
    """Check if content has too many template macros to be useful.

    Returns True if >15% of non-empty lines contain ``{{...}}`` patterns,
    indicating unrendered Jinja2/mkdocs-macros content.
    """
    if "{{" not in content:
        return False
    lines = [ln for ln in content.splitlines() if ln.strip()]
    if len(lines) < 5:
        return False
    macro_lines = 0
    for ln in lines:
        start = ln.find("{{")
        if start != -1 and ln.find("}}", start + 2) != -1:
            macro_lines += 1
    return macro_lines / len(lines) > threshold


def _strip_template_macros(content: str) -> str:
    """Strip lines containing unrendered template macros.

    Removes lines with ``{{...}}`` patterns (Jinja2/mkdocs-macros) that
    produce noise in raw markdown. Keeps the rest of the content intact.
    """
    if "{{" not in content:
        return content
    lines = content.splitlines()
    cleaned = []
    for ln in lines:
        start = ln.find("{{")
        if start != -1 and ln.find("}}", start + 2) != -1:
            continue
        cleaned.append(ln)
    return "\n".join(cleaned)


# Regex matching a URL path segment that is a language code (non-English)
# Matches: /ja/, /de/, /zh-cn/, /pt-br/, /zh-hans/
# Does NOT match: /en/, /api/, /docs/, /v2/
_I18N_URL_SEGMENT_RE = re.compile(
    r"/(?!en(?:[/-]|$))"  # Not English
    r"("
    + "|".join(
        re.escape(str(code))
        for code in sorted(_I18N_LANG_CODES, key=len, reverse=True)
        if code != "en"
    )
    + r")(?=/|$)",
    re.IGNORECASE,
)


def _is_i18n_url(path: str, root_path: str) -> bool:
    """Check if a URL path is a translated (non-English) page.

    Compares the link path against the root docs path to detect language
    code segments that appear in the link but not in the root.
    This avoids false positives when ``en`` appears in the root path.

    Examples::

        _is_i18n_url("/ja/6.0/tutorial/", "/en/6.0/")  -> True
        _is_i18n_url("/en/6.0/tutorial/", "/en/6.0/")  -> False
        _is_i18n_url("/docs/tutorial/",   "/docs/")     -> False
        _is_i18n_url("/de/docs/models/",  "/")          -> True
    """
    # Only flag as i18n if the lang segment is NOT in the root path
    match = _I18N_URL_SEGMENT_RE.search(path)
    if not match:
        return False

    lang_segment = match.group(1).lower()
    # If the root path also has this segment, it's not a translation branch
    # (e.g. the site IS the German version)
    return f"/{lang_segment}/" not in root_path.lower()


def _score_url_by_query(url: str, query_words: frozenset[str]) -> int:
    """Score a URL based on query term overlap in its path."""
    # Performance Optimization: urlparse() is slow and allocates objects.
    # In this hot loop, we manually slice the path using str.find() for standard
    # HTTP(S) URLs (~30% faster). We fallback to urlparse for auth/IPv6 edge cases.
    if url.startswith(("http://", "https://")) and "@" not in url and "[" not in url:
        start = url.find("://") + 3

        end1 = url.find("?", start)
        end2 = url.find("#", start)
        if end1 == -1 and end2 == -1:
            end = len(url)
        elif end1 == -1:
            end = end2
        elif end2 == -1:
            end = end1
        else:
            end = min(end1, end2)

        path_start = url.find("/", start, end)
        if path_start == -1:
            path = ""
        else:
            path = url[path_start:end].lower()
    else:
        path = urlparse(url).path.lower()

    path_words = set(
        path.replace("-", " ")
        .replace("_", " ")
        .replace("/", " ")
        .replace(".", " ")
        .split()
    )
    return len(query_words & path_words)


def _sort_urls_by_query(urls: list[str], query: str) -> list[str]:
    """Sort URLs by query term overlap (highest first)."""
    if not query or not urls:
        return urls
    query_words = frozenset(query.lower().split())

    def score_url(url: str) -> int:
        return _score_url_by_query(url, query_words)

    return sorted(urls, key=score_url, reverse=True)


async def _fetch_github_readme(repo_url: str) -> list[dict] | None:
    """Fetch just the README.md from a GitHub repository.

    Last-resort fallback when all other tiers fail.  Returns chunked
    README content so at least *some* documentation is available.
    """
    match = _GH_REPO_RE.search(repo_url)
    if not match:
        return None

    owner, repo = match.group(1), match.group(2)

    async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(
        timeout=15, follow_redirects=True
    ) as client:
        # Try common README filenames on HEAD (avoids an API call to
        # resolve default branch).
        for fname in (
            "README.md",
            "README.rst",
            "readme.md",
            "README.markdown",
            "Readme.md",
        ):
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{fname}"
            try:
                resp = await client.get(raw_url)
                if resp.status_code != 200 or len(resp.text) < 50:
                    continue
                content = resp.text
                if fname.lower().endswith(".rst"):
                    content = pkg_attr("_rst_to_markdown", _rst_to_markdown)(content)

                gh_page_url = f"https://github.com/{owner}/{repo}"
                chunks = pkg_attr("chunk_markdown", chunk_markdown)(
                    content=content, url=gh_page_url
                )
                if chunks:
                    return chunks
            except Exception:
                continue
    return None


async def _try_github_raw_docs(
    repo_url: str,
    max_files: int = 50,
    library_hint: str = "",
) -> list[dict] | None:
    """Fetch raw markdown docs from a GitHub repository.

    Uses GitHub API to list docs directories and fetch raw ``.md`` files.
    Produces cleaner content than crawling rendered HTML pages.

    Smart filtering:
    - Skips non-English translations (i18n detection)
    - Prefers top-level ``docs/`` over deeply nested doc directories
    - Deprioritizes README.md (appended last)
    - Skips files with excessive template macros (unrendered Jinja2)

    Args:
        repo_url: URL containing ``github.com/owner/repo``
        max_files: Maximum number of markdown files to fetch

    Returns:
        List of ``{url, title, content}`` dicts if successful, ``None`` otherwise.
    """
    match = _GH_REPO_RE.search(repo_url)
    if not match:
        return None

    owner, repo = match.group(1), match.group(2)
    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}"

    async with pkg_attr("_safe_httpx_client", _safe_httpx_client)(timeout=20) as client:
        # Resolve default branch
        try:
            resp = await client.get(
                api_base,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    **pkg_attr("_github_headers", _github_headers)(),
                },
            )
            if resp.status_code != 200:
                return None
            default_branch = resp.json().get("default_branch", "main")
        except Exception:
            return None

        # Collect all candidate markdown files from tree API
        candidate_paths: list[str] = []
        try:
            resp = await client.get(
                f"{api_base}/git/trees/{default_branch}?recursive=1",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    **pkg_attr("_github_headers", _github_headers)(),
                },
            )
            if resp.status_code != 200:
                return None

            tree = resp.json().get("tree", [])
            for item in tree:
                if item.get("type") != "blob":
                    continue
                path = item.get("path", "")
                path_lower = path.lower()

                # Skip .github/ directory files (templates, workflows)
                if path_lower.startswith(".github/"):
                    continue

                # Skip known non-doc files by stem
                fname = path.rsplit("/", 1)[-1]
                stem = fname.rsplit(".", 1)[0].lower()
                if stem in _SKIP_FILES:
                    continue

                # Include root README.md
                if path_lower == "readme.md" or path_lower == "readme.rst":
                    candidate_paths.append(path)
                    continue

                # Only markdown and RST files
                if not path_lower.endswith((".md", ".mdx", ".rst")):
                    continue

                # Must be in a docs-like directory
                parts = path.split("/")
                if not _DOC_DIRS.isdisjoint(p.lower() for p in parts):
                    candidate_paths.append(path)
        except Exception:
            return None

        if not candidate_paths:
            return None

        # Apply smart filtering (i18n, depth priority, README last, framework)
        filtered_paths, has_primary = _filter_doc_paths(
            candidate_paths, library_hint=library_hint
        )

        if not filtered_paths:
            return None

        # If no top-level docs/ directory found, the repo likely keeps
        # user-facing docs on a separate site (e.g. react.dev, angular.dev).
        # Skip GitHub raw fallback so Tier 2 (crawl docs site) is used.
        if not has_primary:
            logger.info(
                f"Skipping GitHub raw docs for {owner}/{repo}: "
                "no top-level docs directory found (only nested/internal docs)"
            )
            return None

        # Fetch raw content for each markdown file
        pages: list[dict] = []
        skipped_macros = 0
        fetch_original_bytes = 0
        fetch_stripped_bytes = 0

        # Up to 50 files are fetched here, so they go out together rather than
        # one after another; sequentially this is the slowest step in the tier.
        # The semaphore keeps the fan-out inside GitHub's rate limit for raw.
        sem = asyncio.Semaphore(10)

        async def _fetch_single_file(fpath: str) -> dict | None:
            raw_url = f"{raw_base}/{default_branch}/{fpath}"
            try:
                async with sem:
                    resp = await client.get(raw_url)
                if resp.status_code != 200:
                    return None
                content = resp.text
                if len(content) < 50:
                    return None
                return {"fpath": fpath, "content": content}
            except Exception:
                return None

        tasks = [_fetch_single_file(f) for f in filtered_paths[:max_files]]
        results = await asyncio.gather(*tasks)

        for res in results:
            if not res:
                continue

            fpath = res["fpath"]
            content = res["content"]

            try:
                # Skip files with excessive template macros;
                # strip scattered macros from otherwise useful files
                if _has_excessive_macros(content):
                    skipped_macros += 1
                    continue

                original_len = len(content)
                content = _strip_template_macros(content)
                fetch_original_bytes += original_len
                fetch_stripped_bytes += len(content)

                # Convert RST to Markdown for consistent chunking
                if fpath.lower().endswith(".rst"):
                    content = pkg_attr("_rst_to_markdown", _rst_to_markdown)(content)

                # Derive title from filename
                fname = fpath.rsplit("/", 1)[-1]
                title = fname.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")

                gh_page_url = (
                    f"https://github.com/{owner}/{repo}/blob/{default_branch}/{fpath}"
                )
                pages.append(
                    {
                        "url": gh_page_url,
                        "title": title,
                        "content": content,
                    }
                )
            except Exception:
                continue

        if skipped_macros:
            logger.info(
                f"Skipped {skipped_macros} files with excessive template macros"
            )

        # Quality gate: if the repo uses heavy templating (many files skipped
        # or significant content lost to macro stripping), fall through to
        # Tier 2 crawl where the docs build system renders macros properly.
        total_files = skipped_macros + len(pages)
        if total_files >= 5 and skipped_macros > 0:
            skip_ratio = skipped_macros / total_files
            content_loss = (
                1 - fetch_stripped_bytes / fetch_original_bytes
                if fetch_original_bytes > 0
                else 0
            )
            if skip_ratio > 0.25 or content_loss > 0.10:
                logger.info(
                    f"Heavy templating in {owner}/{repo}: "
                    f"{skipped_macros}/{total_files} files skipped, "
                    f"{content_loss:.0%} content lost to macros. "
                    "Falling through to crawl"
                )
                return None

        if pages:
            logger.info(
                f"Fetched {len(pages)} raw markdown docs from github.com/{owner}/{repo}"
            )
            return pages

    return None
