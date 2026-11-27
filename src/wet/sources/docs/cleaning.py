"""Documentation content cleaning and blocked-page detection."""

from __future__ import annotations

import re
from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Content cleaning — strip noise before chunking
# ---------------------------------------------------------------------------

# Badge/shield image patterns
_BADGE_RE = re.compile(
    r"!\[.*?\]\(https?://(?:img\.shields\.io|badge\.|badges\.|github\.com/.*?/badge).*?\)",
    re.IGNORECASE,
)
# YAML frontmatter (--- ... ---)
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
# mkdocs admonition blocks (!!! note "Title" ... indented content)
_ADMONITION_RE = re.compile(
    r"^!!!?\s+(?:note|tip|warning|info|danger|example|quote|abstract|"
    r"success|failure|bug|todo|question|hint|caution|attention|important|seealso)"
    r"(?:\s+\"[^\"]*\")?\s*\n(?:(?:\s{4}|\t).*\n)*",
    re.MULTILINE | re.IGNORECASE,
)
# mkdocstrings directives (::: module.path)
_MKDOCSTRINGS_RE = re.compile(r"^:::.*$", re.MULTILINE)
# HTML tags (standalone, not inside code blocks)
_HTML_TAG_RE = re.compile(
    r"<(?!code|pre)[a-z][^>]*>|</(?!code|pre)[a-z][^>]*>", re.IGNORECASE
)
# TOC anchor links (- [Title](#anchor))
_TOC_LINK_RE = re.compile(r"^\s*[-*]\s*\[.*?\]\(#[^)]*\)\s*$", re.MULTILINE)
# Navigation line patterns
_NAV_RE = re.compile(
    r"^\s*(?:"
    r"\u2190 Previous|Next \u2192|Skip to (?:main )?content|"
    r"Table of [Cc]ontents|On this page|"
    r"Edit (?:this|on) (?:page|GitHub)|"
    r"Suggest (?:changes|edits)|"
    r"Was this (?:page|article) helpful\?|"
    r"\u2b50 Star (?:us|this)"
    r")",
    re.IGNORECASE,
)
# Footer boilerplate
_FOOTER_RE = re.compile(
    r"^\s*(?:"
    r"Built with|Powered by|Made with|Generated (?:by|with)|"
    r"Copyright\s*(?:\u00a9|\(c\))|\u00a9\s*\d{4}|"
    r"All [Rr]ights [Rr]eserved"
    r")",
    re.IGNORECASE,
)
# Navigation link line: bullet or number + markdown link with full URL
_NAV_LINK_LINE_RE = re.compile(
    r"^\s*[-*]\s+(?:\[.*?\]\s*)?\[.*?\]\(https?://.*?\)\s*$"
    r"|^\s*\d+\.\s+\[.*?\]\(https?://.*?\)\s*$",
)

# Patterns that indicate a TOC line (not actual content)
_TOC_LINE_RE = re.compile(
    r"^[-*]\s*\[.+?\]\(.+?\)\s*$"  # - [Title](url) or * [Title](url)
    r"|^\[.+?\]\(.+?\)\s*$"  # [Title](url) bare
    r"|^https?://\S+\s*$"  # bare URL
    r"|^>\s*[-*]?\s*\[.+?\]\(.+?\)"  # > - [Title](url) quoted
)

_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# MkDocs UI artifacts that leak into crawled markdown
_MKDOCS_UI_RE = re.compile(
    r"^\s*(?:"
    r"Initializing search|Toggle (?:navigation|search)|Search"
    r"|Back to top|Share\b|Go to repository"
    r")\s*$",
    re.IGNORECASE,
)

# Combined noise filtering pattern
_COMBINED_NOISE_RE = re.compile(
    _NAV_RE.pattern + r"|" + _FOOTER_RE.pattern + r"|" + _MKDOCS_UI_RE.pattern,
    re.IGNORECASE,
)

# Minimum consecutive nav-link lines to consider it a navigation block
_NAV_BLOCK_MIN_LINES = 8


def _strip_nav_blocks(lines: Sequence[str]) -> list[str]:
    """Remove navigation sidebar blocks from crawled content.

    Detects blocks of 8+ consecutive lines that look like site navigation
    (bullet/numbered lists with full-URL markdown links) and removes them.
    This targets MkDocs Material sidebars, Sphinx toctrees, and similar
    navigation structures that leak into crawled markdown.
    """
    result: list[str] = []
    nav_block: list[str] = []

    for line in lines:
        if _NAV_LINK_LINE_RE.match(line):
            nav_block.append(line)
        else:
            if len(nav_block) >= _NAV_BLOCK_MIN_LINES:
                # Navigation block detected — discard it
                pass
            else:
                # Short link list — keep it (could be legitimate content)
                result.extend(nav_block)
            nav_block = []
            result.append(line)

    # Handle trailing nav block
    if len(nav_block) < _NAV_BLOCK_MIN_LINES:
        result.extend(nav_block)

    return result


def _strip_nav_heading_blocks(lines: Sequence[str]) -> list[str]:
    """Remove navigation-like blocks of consecutive headings.

    Navigation sidebars from rendered HTML sometimes produce long sequences
    of same-level headings with no meaningful content between them::

        ## Flexbox & Grid
        ## Spacing
        ## Sizing
        ## Typography
        ## Tables

    When 5+ consecutive headings at the same level have <= 50 chars of text
    between them, they are stripped as navigation artifacts.
    """
    # Build heading map: line_index -> (level, text)
    headings: dict[int, tuple[int, str]] = {}
    for i, line in enumerate(lines):
        # The prefix test is redundant with the pattern and deliberate: most
        # lines in a document are not headings, and this keeps the regex engine
        # off them.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            m = _ANY_HEADING_RE.match(stripped)
            if m:
                headings[i] = (len(m.group(1)), m.group(2))

    if len(headings) < 5:
        return list(lines)

    # Find runs of same-level headings with minimal content between them
    nav_lines: set[int] = set()
    heading_indices = sorted(headings.keys())

    i = 0
    while i < len(heading_indices):
        start_idx = heading_indices[i]
        level = headings[start_idx][0]
        run = [start_idx]

        j = i + 1
        while j < len(heading_indices):
            idx = heading_indices[j]
            if headings[idx][0] != level:
                break
            # Content between this heading and previous must be minimal
            prev_idx = run[-1]
            # Accumulate the length instead of joining the lines: the budget is
            # 50 characters, so most gaps are decided within a line or two and
            # the join would have built a string only to measure it.
            content_length = 0
            is_over_length = False
            for k in range(prev_idx + 1, idx):
                content_length += len(lines[k].strip())
                if content_length > 50:
                    is_over_length = True
                    break
            if is_over_length:
                break

            run.append(idx)
            j += 1

        if len(run) >= 5:
            nav_lines.update(run)

        # Skip to `j` whether or not the run was long enough to strip. The inner
        # loop stops at `j` for a reason that does not depend on where the run
        # started — a level change at `j`, or more than 50 chars of content just
        # before it — so a run restarted anywhere in [i+1, j-1] breaks at the
        # same `j` and is strictly shorter. Restarting at `i + 1` would rescan
        # those headings only to reach the same conclusion.
        i = j

    if not nav_lines:
        return list(lines)

    return [line for i, line in enumerate(lines) if i not in nav_lines]


# Patterns that indicate a page was blocked by bot protection (Cloudflare,
# hCaptcha, reCAPTCHA, etc.).  When all crawled pages match these patterns
# the content is useless; filtering them lets fallback tiers take over.
_BLOCKED_MARKERS = (
    "performing security verification",
    "sicherheitsüberprüfung",  # German CF
    "przeprowadzanie weryfikacji",  # Polish CF
    "biztonsági ellenőrzés",  # Hungarian CF
    "beveiliging wordt geverifieerd",  # Dutch CF
    "vérification de sécurité",  # French CF
    "verificación de seguridad",  # Spanish CF
    "verifica di sicurezza",  # Italian CF
    "enable javascript and cookies to continue",
    "just a moment...",  # legacy CF interstitial
    "challenges.cloudflare.com",
    "cf-chl-widget",
    "_cf_chl_opt",
    "turnstile",  # CF Turnstile widget
    "hcaptcha.com",
    "g-recaptcha",
    "ray id:",  # CF Ray ID (alone is weak, combined with short content)
)


def _is_blocked_content(content: str) -> bool:
    """Detect Cloudflare / CAPTCHA challenge pages.

    Returns True when the crawled content appears to be a bot-protection
    interstitial rather than real documentation.
    """
    if not content:
        return False
    lower = content.lower()
    # Count how many blocked markers appear
    # Bolt optimization: inline for-loop to eliminate generator overhead
    hits = 0
    for marker in _BLOCKED_MARKERS:
        if marker in lower:
            hits += 1
            if hits >= 2:
                break
    # A single "Ray ID" in a long page isn't enough; require 2+ markers
    # or a single strong marker in a short page (< 2000 chars).
    if hits >= 2:
        return True
    if hits == 1 and len(content) < 2000:
        return True
    return False


def _clean_doc_content(content: str) -> str:
    """Strip noise from crawled documentation content.

    Removes badges, YAML frontmatter, mkdocs directives, mkdocstrings,
    HTML tags, TOC anchor links, navigation elements, footer boilerplate,
    navigation sidebar blocks, and navigation heading blocks.
    Applied before chunking to reduce index noise.
    """
    # Remove YAML frontmatter (must be at start of content)
    content = _FRONTMATTER_RE.sub("", content)

    # Remove badge images
    content = _BADGE_RE.sub("", content)

    # Remove mkdocs admonition blocks (keep content readable)
    content = _ADMONITION_RE.sub("", content)

    # Remove mkdocstrings directives
    content = _MKDOCSTRINGS_RE.sub("", content)

    # Remove standalone HTML tags (not code/pre)
    content = _HTML_TAG_RE.sub("", content)

    # Remove TOC anchor links (- [Title](#section))
    content = _TOC_LINK_RE.sub("", content)

    # The line-oriented passes below hand a list[str] to one another and the
    # text is rejoined once at the end. Each of them taking and returning a
    # string would split and join the whole document again.
    lines = content.splitlines()

    # Remove navigation sidebar blocks (MkDocs Material, Sphinx, etc.)
    lines = _strip_nav_blocks(lines)

    # Remove navigation heading blocks (## Topic A / ## Topic B / ...)
    lines = _strip_nav_heading_blocks(lines)

    # Filter noise lines
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if _COMBINED_NOISE_RE.match(stripped):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)
