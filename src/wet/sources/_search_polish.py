"""Lightweight search polish helpers (Phase 1, Task 5).

Adds three concerns on top of the SearXNG result:

1. ``normalize_query`` -- lightweight pre-search normalization (lowercase +
   punctuation collapsing). NOT a synonym expansion: WordNet/nltk pulls in
   ~30MB of data files and a heavy install. Synonym lookup is deferred to
   Phase 2 if metric targets are missed.

2. ``standardize_citation`` -- normalizes one SearXNG result dict into the
   canonical citation shape ``{title, url, snippet, source_domain,
   published_at?, freshness_signal}`` and applies a 200-token snippet cap.

3. ``cap_snippet_tokens`` -- approximates token count via whitespace split
   so the helper has zero deps. Sufficient for Phase 1 -- a real tokenizer
   can be wired in Phase 2 when LLM-cost telemetry is in place.

Freshness signal semantics: derived from the cache age the caller passes
in. Callers pass ``cache_age_seconds=None`` for fresh fetches, an integer
otherwise; values past half the action's TTL are flagged ``stale``.
"""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

# Punctuation characters we collapse to a single space during normalization.
# Keeps alphanumerics + chars meaningful to search operators
# (`-` exclude, `:` site/intitle, `.` domains, `/` paths, `"` `'` quoted phrase).
_PUNCT_RE = re.compile(r"[^\w\s\-\.\"':/]+")

# Token cap for snippets returned to the model.
_SNIPPET_TOKEN_CAP = 200

# Freshness threshold: results older than half the TTL are "stale".
_FRESHNESS_RATIO = 0.5


def normalize_query(q: str) -> str:
    """Lowercase + collapse punctuation/whitespace.

    No stemming, no synonym lookup. See module docstring for trade-offs.
    """
    if not q:
        return ""
    lowered = q.strip().lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return " ".join(no_punct.split())


def cap_snippet_tokens(snippet: str, max_tokens: int = _SNIPPET_TOKEN_CAP) -> str:
    """Cap a snippet to ``max_tokens`` whitespace-separated tokens.

    Whitespace split approximates tokens within a small constant factor
    for English text -- good enough for a defensive cap.
    """
    if not snippet:
        return ""
    # Optimization: Use maxsplit to avoid parsing the entire string
    # when the snippet significantly exceeds max_tokens.
    tokens = snippet.split(None, max_tokens)
    if len(tokens) <= max_tokens:
        return snippet
    return " ".join(tokens[:max_tokens]) + "..."


def _source_domain(url: str) -> str:
    """Extract the registrable domain (netloc) from a URL."""
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc
    except (ValueError, TypeError):
        return ""
    # Strip port and leading 'www.' for cleaner display.
    netloc = netloc.split(":", 1)[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def freshness_signal(
    cache_age_seconds: int | None,
    ttl_seconds: int,
) -> str:
    """Return ``"fresh"`` or ``"stale"`` based on cache age.

    - ``cache_age_seconds is None`` -> ``"fresh"`` (just fetched).
    - ``cache_age_seconds <= ttl * 0.5`` -> ``"fresh"``.
    - otherwise -> ``"stale"``.
    """
    if cache_age_seconds is None:
        return "fresh"
    if ttl_seconds <= 0:
        return "stale"
    return "fresh" if cache_age_seconds <= ttl_seconds * _FRESHNESS_RATIO else "stale"


def standardize_citation(
    raw: dict[str, Any],
    *,
    cache_age_seconds: int | None = None,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    """Normalize one search result into the canonical citation shape.

    Required output keys: ``title``, ``url``, ``snippet``, ``source_domain``,
    ``freshness_signal``. Optional: ``published_at`` (only present when the
    upstream supplied it). Original keys are preserved alongside the
    normalized ones so existing reranker/enrichment code continues to work.
    """
    url = raw.get("url", "") or ""
    snippet = raw.get("snippet") or raw.get("content") or ""
    title = raw.get("title", "") or ""

    out: dict[str, Any] = dict(raw)
    out["title"] = title
    out["url"] = url
    out["snippet"] = cap_snippet_tokens(snippet)
    out["source_domain"] = _source_domain(url)
    out["freshness_signal"] = freshness_signal(cache_age_seconds, ttl_seconds)

    published_at = raw.get("published_at") or raw.get("publishedDate")
    if published_at:
        out["published_at"] = published_at

    # Attach finite confidence if available in raw result (e.g. rerank/similarity score)
    score_keys = (
        "score",
        "confidence",
        "relevance",
        "similarity",
        "similarity_score",
        "rerank_score",
    )
    for k in score_keys:
        val = raw.get(k)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            import math

            if not (math.isnan(val) or math.isinf(val)):
                out["confidence"] = round(float(val), 4)
                break

    return out


def standardize_results(
    results: list[dict[str, Any]],
    *,
    cache_age_seconds: int | None = None,
    ttl_seconds: int = 3600,
) -> list[dict[str, Any]]:
    """Apply ``standardize_citation`` to a list of results."""
    return [
        standardize_citation(
            r,
            cache_age_seconds=cache_age_seconds,
            ttl_seconds=ttl_seconds,
        )
        for r in results
    ]


def search_ttl_seconds(time_range: str | None) -> int:
    """TTL policy: 300s for time-filtered queries, 3600s otherwise.

    Time-filtered queries (e.g. ``time_range="day"``) should refresh more
    aggressively because the user is asking for recent content.
    """
    return 300 if time_range else 3600


# Refinement (refine=true) quality gate: a round whose mean rerank score
# falls below this floor counts as low quality and triggers one more
# LLM-rewritten round (bounded). Chosen to sit above the point where a
# reranked list is mostly noise; rounds without scores (reranker
# unavailable) are judged on non-emptiness only.
_REFINE_MIN_MEAN_SCORE = 0.35


def round_quality(results: list[dict[str, Any]]) -> float:
    """Mean rerank score of a round's results.

    Empty -> 0.0 (worst). Results carrying no finite numeric ``score`` (the
    reranker was unavailable) -> 1.0: with no quality signal, non-emptiness
    is success and refinement would only burn tokens. Finite guarantee: a
    NaN/inf score is ignored rather than poisoning the mean.
    """
    if not results:
        return 0.0
    scores = [
        float(s)
        for s in (r.get("score") for r in results)
        if isinstance(s, (int, float)) and not isinstance(s, bool) and math.isfinite(s)
    ]
    if not scores:
        return 1.0
    return sum(scores) / len(scores)


def refine_needed(results: list[dict[str, Any]]) -> bool:
    """Whether a round failed the quality gate (empty or low mean score)."""
    return round_quality(results) < _REFINE_MIN_MEAN_SCORE
