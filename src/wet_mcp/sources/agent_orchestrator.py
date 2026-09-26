"""Multi-step research orchestration: search -> extract N -> LLM synthesis.

Phase 3 spec section 4.2 / section 5.6: ``extract(action="agent", query=...)``
runs one search round, extracts up to N URLs concurrently, then asks the
configured LLM to synthesise a citation-preserving Markdown report.

Multi-provider rule (spec section 5.6): there is NO hardcoded default
provider. The orchestrator returns a clear error string if no provider
key is set instead of failing late inside the LLM SDK.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from loguru import logger

from wet_mcp.sources.search_backends import run_search_chain

# LLM-provider key env names, in spec-section-5.6 fallback priority. Checked
# against host-level ``os.environ`` only: per-sub credential buckets were
# removed in the 2026-09 de-host (keys are host-only), so every mode sees the
# same host-configured provider set. GOOGLE_API_KEY is the GEMINI alias;
# ANTHROPIC and XAI round out the cloud chat providers the setup form offers
# (the list previously omitted ANTHROPIC). Aliased here for the tests that
# key off ``ao._PROVIDER_KEYS``.
_PROVIDER_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_VERTEX_EXPRESS_API_KEY",
)

_DEFAULT_MAX_URLS = 5
_HARD_MAX_URLS = 20
_DEFAULT_TOKEN_BUDGET = 10000
# Rough heuristic: 1 token ~ 4 chars; matches what wet's LLM
# layer assumes for prompt sizing in other call sites.
_CHARS_PER_TOKEN = 4
_EXTRACT_CONCURRENCY = 3


def detect_llm_provider() -> str | None:
    """Return the first configured provider key name, or ``None``.

    Reads host-level ``os.environ`` only (order: ``_PROVIDER_KEYS`` fallback
    priority, incl. the GOOGLE->GEMINI alias). Per-sub credential buckets were
    removed in the 2026-09 de-host. ``None`` means the orchestrator should
    bail out with a structured error rather than try.
    """
    for key in _PROVIDER_KEYS:
        if os.getenv(key):
            return key
    return None


def _no_provider_error() -> str:
    return (
        "Error: no LLM provider detected. Set one of "
        "GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / XAI_API_KEY."
    )


def _clamp_max_urls(max_urls: int) -> int:
    return min(max(int(max_urls), 1), _HARD_MAX_URLS)


def _truncate_for_budget(text: str, char_budget: int) -> str:
    if len(text) <= char_budget:
        return text
    return text[:char_budget] + "\n...[truncated for token budget]"


def build_cited_prompt(
    query: str, extracts: list[dict[str, Any]], token_budget: int
) -> str:
    """Build the synthesis prompt with numbered ``[N]`` citations.

    Greedy: each extract is allotted ``token_budget // len(extracts)``
    tokens worth of characters (with a 1-token reservation for the
    framing), preserving order so citation numbers match ``sources``.
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
    return (
        "You are a research assistant. Synthesise a concise, factual "
        "Markdown answer to the user's question using ONLY the numbered "
        "sources below. Preserve numeric citation markers like [1], [2] "
        "wherever you cite a fact, matching the source numbering exactly.\n\n"
        f"User question: {query}\n\n"
        f"Sources:\n\n{sources_block}\n\n"
        "Now produce the synthesised Markdown answer. End with a "
        "'## Sources' section listing each cited [N] as a bullet."
    )


async def _extract_many(urls: list[str]) -> list[dict[str, Any]]:
    """Concurrently extract URLs (sem-bounded).

    Returns a list of smart-chunks-shaped dicts in input order. Lazy import
    keeps cold-start cheap when the agent action is not used.
    """
    from wet_mcp.sources.crawler import extract as crawler_extract

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
    """Call the configured LLM via wet_mcp.llm with the cited prompt."""
    from wet_mcp.llm import acompletion, get_llm_config

    config = get_llm_config()
    model = model_override or config["model"]
    response = await acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.get("temperature"),
        fallbacks=config.get("fallbacks"),
    )
    return str(response.choices[0].message.content)


async def run_agent(
    query: str,
    max_urls: int = _DEFAULT_MAX_URLS,
    synthesis_model: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
) -> dict[str, Any] | str:
    """Run the full research loop and return a structured synthesis dict.

    Returns a string starting with ``"Error: "`` on hard failures so MCP
    callers see the message instead of an exception trace, matching the
    rest of the wet tool surface.
    """
    if not query or not query.strip():
        return "Error: query is required for extract(action=agent)."

    if detect_llm_provider() is None:
        return _no_provider_error()

    max_urls = _clamp_max_urls(max_urls)

    # 1. Search round through the canonical provider chain.
    try:
        raw_search = await run_search_chain(query, max_results=max_urls)
        search_payload = json.loads(raw_search)
        if not isinstance(search_payload, dict):
            raise ValueError("search returned a non-object payload")
    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(f"agent_orchestrator search failed: {error_type}")
        return f"Error: search failed: {error_type}"

    if search_payload.get("error"):
        return f"Error: search failed: {search_payload['error']}"

    raw_results = search_payload.get("results", [])
    if not isinstance(raw_results, list):
        return "Error: search failed: results is not a list"
    selected_results = [
        result
        for result in raw_results
        if isinstance(result, dict) and result.get("url")
    ][:max_urls]
    urls = [str(result["url"]) for result in selected_results]
    if not urls:
        return {
            "markdown": (
                f"No results found for query: {query!r}. Try a different "
                f"phrasing or use search(action='research') for academic queries."
            ),
            "sources": [],
            "per_url_metadata": [],
        }

    # 2. Concurrent extract.
    extracts = await _extract_many(urls)

    # 3. Build cited prompt within token budget.
    prompt = build_cited_prompt(query, extracts, token_budget)

    # 4. Synthesise via LLM.
    try:
        markdown = await _llm_synthesize(prompt, synthesis_model)
    except Exception as exc:
        logger.error(f"agent_orchestrator synthesis failed: {exc}")
        return f"Error: synthesis failed: {exc}"

    sources = []
    for i, extract in enumerate(extracts):
        search_result = selected_results[i] if i < len(selected_results) else {}
        search_provider = str(search_result.get("source") or "")
        sources.append(
            {
                "index": i + 1,
                "url": extract.get("url", urls[i] if i < len(urls) else ""),
                "title": (extract.get("metadata") or {}).get("title")
                or extract.get("title")
                or search_result.get("title", ""),
                "search_provider": search_provider,
            }
        )

    per_url_metadata = []
    for i, extract in enumerate(extracts):
        search_result = selected_results[i] if i < len(selected_results) else {}
        search_provider = str(search_result.get("source") or "")
        per_url_metadata.append(
            {
                "url": extract.get("url", urls[i] if i < len(urls) else ""),
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

    return {
        "markdown": markdown,
        "sources": sources,
        "per_url_metadata": per_url_metadata,
    }
