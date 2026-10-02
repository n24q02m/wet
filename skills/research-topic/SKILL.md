---
name: research-topic
description: Multi-step research orchestration. Use when user asks "research X", "summarize current state of Y", "what's the latest on Z", or compares approaches. Calls extract(action="agent") which searches the web, extracts top results, then synthesises a citation-preserving Markdown answer with one configured LLM.
argument-hint: "<research question>"
---

# research-topic

Drive wet-mcp's `extract(action="agent")` to answer a research question
end to end: one search round + concurrent extracts of the top hits + a
single LLM synthesis pass that preserves numbered `[N]` citations
matching the returned sources.

Use this skill when:
- The user asks an open-ended question that needs multiple sources.
- "Summarise the current state of X."
- "What's the latest on Y?"
- "Compare approaches to Z."
- The user needs a quoted, cited answer (the citations are first-class
  output, not an afterthought).

Do NOT use this skill when:
- The user already gave you a specific URL -- call `extract(action="extract")`.
- The user wants a single search result list -- call `search(action="web")`.
- The question is about library API documentation -- call
  `search(action="docs_query")` against a Tier 1 / locked stack.

## Steps

1. **Restate the question** to the user in 1-2 sentences (calibration:
   confirm scope before spending tokens).

2. **Pick `max_urls`** based on breadth:
   - 3-5 for a tight question (single technology, single timeframe).
   - 6-10 for a broad survey (multiple competitors, multi-year window).
   - Hard ceiling is 20 (cost guard).

3. **Pick `synthesis_model`** only if the user asked for a specific
   model. Otherwise omit and let wet auto-detect from
   `LLM_MODELS` / `GEMINI_API_KEY` / `OPENAI_API_KEY` / `XAI_API_KEY`.

4. **Call**
   ```text
   extract(action="agent", query="<question>", max_urls=<N>)
   ```
   Optional knobs: `synthesis_model="..."`, `token_budget=<int>`
   (default 10000; raise for long-form questions, lower for tight cost
   control).

5. **Quote the synthesised Markdown verbatim** to the user, then list
   the sources from the `sources` array as clickable URLs. If
   `per_url_metadata` shows any `error`, mention which URL failed and
   that the synthesis used the remaining N-K sources.

6. **If wet returns** `Error: no LLM provider detected`, surface the
   exact error to the user (do not silently retry against
   `search(action="research")`); they need to set one of the supported
   API keys before agent works.

## Output contract

```json
{
  "markdown": "# Synthesised answer with [1] inline citations...",
  "sources": [
    {"index": 1, "url": "https://...", "title": "..."}
  ],
  "per_url_metadata": [
    {"url": "...", "extract_strategy": "basic_http", "tokens": 487, "error": null}
  ]
}
```

## Anti-patterns

- Do NOT chain multiple `agent` calls back-to-back without informing
  the user; each call is a full search + N extracts + LLM round.
- Do NOT post-edit the synthesised Markdown to drop citations -- the
  citation markers are the user's audit trail.
- Do NOT replace `extract(action="agent")` with manual
  `search` + `extract` loops "to save tokens"; the orchestrator
  enforces token budgets per source and avoids re-implementation drift.
