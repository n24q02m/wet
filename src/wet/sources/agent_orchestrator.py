"""Multi-step research orchestration: search -> extract N -> LLM synthesis.

Phase 3 spec section 4.2 / section 5.6: ``extract(action="agent", query=...)``
runs one search round, extracts up to N URLs concurrently, then asks the
configured LLM to synthesise a citation-preserving Markdown report.

Steering: a :class:`ResearchDirection` (focus topics, constraints, excluded
sources, remaining follow-up depth) shapes the run. ``run_agent`` calls an
optional ``on_step`` hook at each orchestration checkpoint (before a search
round, before its extraction, before synthesis), so a running job picks up
steering changes at its next step. While depth remains, each unsearched focus
topic adds one follow-up search round. Without steering the run is a single
round, as before.

Multi-provider rule (spec section 5.6): there is NO hardcoded default
provider. The orchestrator returns a clear error string if no provider
key is set instead of failing late inside the LLM SDK.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from urllib.parse import urlsplit

from loguru import logger

from wet.sources.search_backends import run_search_chain

# LLM-provider credential env names, checked before falling back to the
# [models.chat] cell. OPENROUTER_API_KEY is the single-OpenRouter-default
# credential: wet.runtime.model_cell feeds it into any OpenRouter-default
# cell whose key is otherwise unset, so its presence means the chat cell can
# authenticate. HULL_CHAT_API_KEY is the per-task host-injection path and
# always overrides the cell's api_key. Aliased for tests keying off
# ``ao._PROVIDER_KEYS``.
_PROVIDER_KEYS = (
    "OPENROUTER_API_KEY",
    "HULL_CHAT_API_KEY",
)

_DEFAULT_MAX_URLS = 5
_HARD_MAX_URLS = 20
_DEFAULT_TOKEN_BUDGET = 10000
# Rough heuristic: 1 token ~ 4 chars; matches what wet's LLM
# layer assumes for prompt sizing in other call sites.
_CHARS_PER_TOKEN = 4
_EXTRACT_CONCURRENCY = 3

# ---------------------------------------------------------------------------
# Steering
# ---------------------------------------------------------------------------

# Orchestration checkpoints, in run order.
STEP_SEARCH = "search"
STEP_EXTRACT = "extract"
STEP_SYNTHESIZE = "synthesize"

# Follow-up search rounds a run may add for focus topics unless steered.
DEFAULT_REMAINING_DEPTH = 2
MAX_REMAINING_DEPTH = 5
_MAX_STEER_ITEMS = 20
_MAX_STEER_ITEM_CHARS = 200
_STEER_LIST_KEYS = ("add_focus", "remove_focus", "add_constraints", "exclude_sources")
STEER_KEYS = (*_STEER_LIST_KEYS, "depth")
_HOST_RE = re.compile(r"^[a-z0-9_.:-]+$")


@dataclass
class ResearchDirection:
    """Where a research run is heading; steering edits it between steps.

    ``remaining_depth`` counts the follow-up search rounds still allowed.
    """

    focus: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    exclude_sources: list[str] = field(default_factory=list)
    remaining_depth: int = DEFAULT_REMAINING_DEPTH

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> ResearchDirection:
        """Rebuild from stored JSON, ignoring anything malformed."""
        if not isinstance(data, dict):
            return cls()

        def _strings(key: str) -> list[str]:
            value = data.get(key)
            if not isinstance(value, list):
                return []
            return [item for item in value if isinstance(item, str)]

        depth = data.get("remaining_depth")
        if not isinstance(depth, int) or isinstance(depth, bool):
            depth = DEFAULT_REMAINING_DEPTH
        return cls(
            focus=_strings("focus"),
            constraints=_strings("constraints"),
            exclude_sources=_strings("exclude_sources"),
            remaining_depth=min(max(depth, 0), MAX_REMAINING_DEPTH),
        )


# ``on_step(step, round_no, direction)`` returns the direction to continue with.
StepHook = Callable[[str, int, ResearchDirection], Awaitable[ResearchDirection]]


def _steer_error(message: str) -> tuple[None, str]:
    return None, f"Error: {message}"


def _source_host(value: str) -> str:
    """Host name of a URL or bare host, without ``www.``; ``""`` if invalid."""
    target = value if "://" in value else f"//{value}"
    try:
        host = (urlsplit(target).hostname or "").strip(".")
    except ValueError:
        return ""
    host = host.removeprefix("www.")
    return host if _HOST_RE.match(host) else ""


def _dedupe(items: list[str]) -> list[str]:
    """Drop case-insensitive duplicates, keeping the first spelling."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def validate_steering(changes: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Normalise a steering request into ``(changes, None)`` or ``(None, error)``.

    Fields: ``add_focus``, ``remove_focus``, ``add_constraints`` and
    ``exclude_sources`` take a string or a list of strings; ``depth`` (0-5)
    sets how many follow-up search rounds remain. Excluded sources are
    reduced to host names, so ``https://www.example.com/a`` excludes
    ``example.com`` and its subdomains.
    """
    valid = ", ".join(STEER_KEYS)
    if not isinstance(changes, dict):
        return _steer_error(f"steering must be an object with any of: {valid}.")
    unknown = sorted(str(key) for key in changes if key not in STEER_KEYS)
    if unknown:
        return _steer_error(
            f"unknown steering field(s) {', '.join(unknown)}; valid fields: {valid}."
        )

    normalized: dict[str, Any] = {}
    for key in _STEER_LIST_KEYS:
        if key not in changes:
            continue
        raw = changes[key]
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list) or not all(
            isinstance(item, str) for item in values
        ):
            return _steer_error(f"{key} must be a string or a list of strings.")
        cleaned: list[str] = []
        for item in values:
            text = item.strip()
            if not text:
                continue
            if len(text) > _MAX_STEER_ITEM_CHARS:
                return _steer_error(
                    f"{key} entries must be at most {_MAX_STEER_ITEM_CHARS} characters."
                )
            if key == "exclude_sources":
                host = _source_host(text)
                if not host:
                    return _steer_error(
                        f"exclude_sources entry {text!r} is not a host name or URL."
                    )
                text = host
            cleaned.append(text)
        cleaned = _dedupe(cleaned)
        if len(cleaned) > _MAX_STEER_ITEMS:
            return _steer_error(f"{key} accepts at most {_MAX_STEER_ITEMS} entries.")
        if cleaned:
            normalized[key] = cleaned

    if "depth" in changes:
        depth = changes["depth"]
        if (
            not isinstance(depth, int)
            or isinstance(depth, bool)
            or not 0 <= depth <= MAX_REMAINING_DEPTH
        ):
            return _steer_error(
                f"depth must be an integer from 0 to {MAX_REMAINING_DEPTH}."
            )
        normalized["depth"] = depth

    if not normalized:
        return _steer_error(f"steering needs at least one change ({valid}).")
    return normalized, None


def apply_steering(
    direction: ResearchDirection, changes: dict[str, Any]
) -> ResearchDirection:
    """Return ``direction`` with validated ``changes`` applied.

    ``direction`` itself is not modified. Within one change set additions
    apply before removals, so removing a topic always wins.
    """
    removed = {topic.casefold() for topic in changes.get("remove_focus", [])}
    focus = _dedupe([*direction.focus, *changes.get("add_focus", [])])
    return replace(
        direction,
        focus=[topic for topic in focus if topic.casefold() not in removed],
        constraints=_dedupe(
            [*direction.constraints, *changes.get("add_constraints", [])]
        ),
        exclude_sources=_dedupe(
            [*direction.exclude_sources, *changes.get("exclude_sources", [])]
        ),
        remaining_depth=changes.get("depth", direction.remaining_depth),
    )


def is_excluded(url: str, exclude_sources: list[str]) -> bool:
    """Whether ``url`` is on an excluded host or one of its subdomains."""
    if not exclude_sources:
        return False
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    return any(host == ex or host.endswith(f".{ex}") for ex in exclude_sources)


def detect_llm_provider() -> str | None:
    """Return the credential source enabling chat-cell calls, or ``None``.

    Checks host-level ``os.environ`` for ``_PROVIDER_KEYS`` first (the
    OpenRouter single-default and per-task injection paths), then falls back
    to the ``[models.chat]`` cell in ``~/.wet/config.toml`` — a cell api_key
    set in the file never appears in env. ``None`` means the orchestrator
    should bail out with a structured error rather than try.
    """
    for key in _PROVIDER_KEYS:
        if os.getenv(key):
            return key
    from wet.llm import has_llm_provider

    return "[models.chat]" if has_llm_provider() else None


def _no_provider_error() -> str:
    return (
        "Error: no LLM provider detected. Configure the [models.chat] cell in "
        "~/.wet/config.toml (api_key), or set HULL_CHAT_API_KEY / "
        "OPENROUTER_API_KEY."
    )


def _clamp_max_urls(max_urls: int) -> int:
    return min(max(int(max_urls), 1), _HARD_MAX_URLS)


def _truncate_for_budget(text: str, char_budget: int) -> str:
    if len(text) <= char_budget:
        return text
    return text[:char_budget] + "\n...[truncated for token budget]"


def build_cited_prompt(
    query: str,
    extracts: list[dict[str, Any]],
    token_budget: int,
    direction: ResearchDirection | None = None,
) -> str:
    """Build the synthesis prompt with numbered ``[N]`` citations.

    Greedy: each extract is allotted ``token_budget // len(extracts)``
    tokens worth of characters (with a 1-token reservation for the
    framing), preserving order so citation numbers match ``sources``.
    Steered focus topics and constraints are added when ``direction`` has
    any.
    """
    if not extracts:
        return (
            f"You are a research assistant. The user asked: {query!r}\n"
            "No sources could be extracted; reply that no information is "
            "available rather than inventing one."
        )

    per_extract_chars = max(
        200, ((token_budget - 200) // max(len(extracts), 1)) * _CHARS_PER_TOKEN
    )

    citation_blocks: list[str] = []
    for idx, extract in enumerate(extracts, start=1):
        url = extract.get("url", "")
        # smart_chunks output uses ``markdown`` or ``clean_text``; document
        # bridge uses ``content``. Try them in priority order.
        body = (
            extract.get("markdown")
            or extract.get("clean_text")
            or extract.get("content")
            or extract.get("error", "")
        )
        body = _truncate_for_budget(body, per_extract_chars)
        title = (extract.get("metadata") or {}).get("title") or extract.get(
            "title", url
        )
        citation_blocks.append(f"[{idx}] {title}\nURL: {url}\n---\n{body}\n---")

    sources_block = "\n\n".join(citation_blocks)
    steering_lines: list[str] = []
    if direction is not None and direction.focus:
        steering_lines.append(f"Focus on: {'; '.join(direction.focus)}")
    if direction is not None and direction.constraints:
        steering_lines.append(
            f"Constraints to respect: {'; '.join(direction.constraints)}"
        )
    steering_block = "".join(f"{line}\n" for line in steering_lines)
    if steering_block:
        steering_block += "\n"
    return (
        "You are a research assistant. Synthesise a concise, factual "
        "Markdown answer to the user's question using ONLY the numbered "
        "sources below. Preserve numeric citation markers like [1], [2] "
        "wherever you cite a fact, matching the source numbering exactly.\n\n"
        f"User question: {query}\n\n"
        f"{steering_block}"
        f"Sources:\n\n{sources_block}\n\n"
        "Now produce the synthesised Markdown answer. End with a "
        "'## Sources' section listing each cited [N] as a bullet."
    )


async def _extract_many(urls: list[str]) -> list[dict[str, Any]]:
    """Concurrently extract URLs (sem-bounded).

    Returns a list of smart-chunks-shaped dicts in input order. Lazy import
    keeps cold-start cheap when the agent action is not used.
    """
    from wet.sources.crawler import extract as crawler_extract

    sem = asyncio.Semaphore(_EXTRACT_CONCURRENCY)

    async def _one(url: str) -> dict[str, Any]:
        async with sem:
            try:
                raw = await crawler_extract(urls=[url])
            except Exception as exc:  # pragma: no cover - bubbled in summary
                logger.error(f"agent_orchestrator extract failed {url}: {exc}")
                return {"url": url, "error": str(exc)}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"url": url, "error": "extract returned non-JSON payload"}
            if isinstance(parsed, list) and parsed:
                return parsed[0]
            return {"url": url, "error": "extract returned empty payload"}

    return await asyncio.gather(*(_one(u) for u in urls))


async def _llm_synthesize(prompt: str, model_override: str | None) -> str:
    """Call the configured LLM via wet.llm with the cited prompt."""
    from wet.llm import acompletion, get_llm_config

    config = get_llm_config()
    model = model_override or config["model"]
    response = await acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.get("temperature"),
        fallbacks=config.get("fallbacks"),
    )
    return str(response.choices[0].message.content)


def _no_results(query: str, *, excluded: bool = False) -> dict[str, Any]:
    if excluded:
        markdown = (
            f"No sources left for query: {query!r}. Steering excluded every "
            "extracted source; remove an exclusion or start a new job."
        )
    else:
        markdown = (
            f"No results found for query: {query!r}. Try a different "
            f"phrasing or use search(action='research') for academic queries."
        )
    return {"markdown": markdown, "sources": [], "per_url_metadata": []}


async def _search_round(
    query: str, max_results: int
) -> tuple[list[dict[str, Any]], str | None]:
    """Run one search through the provider chain.

    Returns ``(results, None)`` with the results that carry a URL, or
    ``([], error)`` with an ``"Error: ..."`` string.
    """
    try:
        raw_search = await run_search_chain(query, max_results=max_results)
        search_payload = json.loads(raw_search)
        if not isinstance(search_payload, dict):
            raise ValueError("search returned a non-object payload")
    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(f"agent_orchestrator search failed: {error_type}")
        return [], f"Error: search failed: {error_type}"

    if search_payload.get("error"):
        return [], f"Error: search failed: {search_payload['error']}"

    raw_results = search_payload.get("results", [])
    if not isinstance(raw_results, list):
        return [], "Error: search failed: results is not a list"
    return [
        result
        for result in raw_results
        if isinstance(result, dict) and result.get("url")
    ], None


def _next_topic(
    direction: ResearchDirection,
    searched: set[str],
    picked: int,
    round_no: int,
) -> str | None:
    """The focus topic for the next search round, or None to synthesise."""
    if (
        direction.remaining_depth <= 0
        or picked >= _HARD_MAX_URLS
        or round_no > MAX_REMAINING_DEPTH
    ):
        return None
    for topic in direction.focus:
        if topic.casefold() not in searched:
            return topic
    return None


async def run_agent(
    query: str,
    max_urls: int = _DEFAULT_MAX_URLS,
    synthesis_model: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    *,
    direction: ResearchDirection | None = None,
    on_step: StepHook | None = None,
) -> dict[str, Any] | str:
    """Run the full research loop and return a structured synthesis dict.

    Returns a string starting with ``"Error: "`` on hard failures so MCP
    callers see the message instead of an exception trace, matching the
    rest of the wet tool surface.

    ``direction`` seeds the steering state. ``on_step(step, round, direction)``
    is awaited before each search round, before each extraction and before
    synthesis, and returns the direction to continue with. Excluded sources
    are dropped before extraction and again before synthesis. While
    ``remaining_depth`` allows, each unsearched focus topic runs one follow-up
    round (``"<query> <topic>"``) that skips URLs already extracted; all
    rounds together extract at most 20 URLs.
    """
    if not query or not query.strip():
        return "Error: query is required for extract(action=agent)."

    if detect_llm_provider() is None:
        return _no_provider_error()

    max_urls = _clamp_max_urls(max_urls)
    current = direction or ResearchDirection()

    async def checkpoint(step: str, round_no: int) -> None:
        nonlocal current
        if on_step is not None:
            current = await on_step(step, round_no, current)

    # (search result, extract) per extracted URL, in citation order.
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[str] = set()
    searched: set[str] = set()
    stopped = False
    round_no = 1
    round_query = query
    await checkpoint(STEP_SEARCH, round_no)

    while True:
        # 1. Search round through the canonical provider chain, over-fetching
        # enough to cover exclusions and URLs earlier rounds already took.
        max_results = min(
            max_urls + len(current.exclude_sources) + len(seen), _HARD_MAX_URLS
        )
        results, error = await _search_round(round_query, max_results)
        if error is not None and round_no == 1:
            return error
        if error is not None:
            # A failed follow-up round keeps what earlier rounds found.
            logger.warning(f"agent_orchestrator follow-up round stopped: {error}")
            stopped = True
        fresh: dict[str, dict[str, Any]] = {}
        for result in results:
            url = str(result["url"])
            if url not in seen:
                fresh.setdefault(url, result)

        # 2. Concurrent extract of the URLs this round adds.
        if fresh:
            await checkpoint(STEP_EXTRACT, round_no)
            room = _HARD_MAX_URLS - len(pairs)
            batch = [
                result
                for url, result in fresh.items()
                if not is_excluded(url, current.exclude_sources)
            ][: min(max_urls, room)]
            if batch:
                urls = [str(result["url"]) for result in batch]
                seen.update(urls)
                for i, extract in enumerate(await _extract_many(urls)):
                    pairs.append((batch[i] if i < len(batch) else {}, extract))

        # 3. Next step: a follow-up round for an unsearched focus topic, or
        # synthesis. Re-check after the checkpoint, since the steering it
        # applied can switch between the two.
        topic = (
            None if stopped else _next_topic(current, searched, len(pairs), round_no)
        )
        while True:
            if topic is not None:
                await checkpoint(STEP_SEARCH, round_no + 1)
            else:
                await checkpoint(STEP_SYNTHESIZE, round_no)
            following = (
                None
                if stopped
                else _next_topic(current, searched, len(pairs), round_no)
            )
            switched = (following is None) != (topic is None)
            topic = following
            if not switched:
                break
        if topic is None:
            break
        searched.add(topic.casefold())
        current = replace(current, remaining_depth=current.remaining_depth - 1)
        round_no += 1
        round_query = f"{query} {topic}"

    kept = [
        (result, extract)
        for result, extract in pairs
        if not is_excluded(
            str(extract.get("url") or result.get("url") or ""),
            current.exclude_sources,
        )
    ]
    if not kept:
        return _no_results(query, excluded=bool(pairs))
    extracts = [extract for _, extract in kept]

    # 4. Build cited prompt within token budget.
    prompt = build_cited_prompt(query, extracts, token_budget, current)

    # 5. Synthesise via LLM.
    try:
        markdown = await _llm_synthesize(prompt, synthesis_model)
    except Exception as exc:
        logger.error(f"agent_orchestrator synthesis failed: {exc}")
        return f"Error: synthesis failed: {exc}"

    sources = []
    for i, (search_result, extract) in enumerate(kept):
        search_provider = str(search_result.get("source") or "")
        sources.append(
            {
                "index": i + 1,
                "url": extract.get("url", str(search_result.get("url") or "")),
                "title": (extract.get("metadata") or {}).get("title")
                or extract.get("title")
                or search_result.get("title", ""),
                "search_provider": search_provider,
            }
        )

    per_url_metadata = []
    for search_result, extract in kept:
        search_provider = str(search_result.get("source") or "")
        per_url_metadata.append(
            {
                "url": extract.get("url", str(search_result.get("url") or "")),
                "extract_strategy": (extract.get("metadata") or {}).get(
                    "scrape_strategy_used", ""
                ),
                "tokens": len(
                    extract.get("markdown")
                    or extract.get("clean_text")
                    or extract.get("content")
                    or ""
                )
                // _CHARS_PER_TOKEN,
                "error": extract.get("error"),
                "search_provider": search_provider,
            }
        )

    verification: dict[str, Any] | None = None
    try:
        from wet.sources.agent_jobs import verify_citations

        verification = verify_citations(markdown, sources, extracts)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Citation verification skipped: {exc}")

    return {
        "markdown": markdown,
        "sources": sources,
        "per_url_metadata": per_url_metadata,
        **({"verification": verification} if verification is not None else {}),
    }
