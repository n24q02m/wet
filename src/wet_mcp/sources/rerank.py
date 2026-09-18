"""Optional Cohere rerank post-processing for the web-search chain.

Cohere's ``rerank`` API is a PAID provider, so this layer is double opt-in:
``COHERE_API_KEY`` must be present AND ``WET_SEARCH_RERANK=1`` set. Rerank
failures never fail the search: the original ordering is kept and a warning
logged. Single-user env/settings only for now — the subject-aware search
config helpers live in ``search_backends`` and would import-cycle here.
"""

from __future__ import annotations

import logging

import httpx

from wet_mcp.config import settings

logger = logging.getLogger(__name__)


class CohereReranker:
    """Cohere ``/v2/rerank`` client over the shared result-shape dicts."""

    name = "cohere"

    def __init__(self, key: str, *, model: str, base_url: str) -> None:
        self.key = key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def rerank(self, query: str, results: list[dict], top_n: int) -> list[dict]:
        """Return ``results`` reordered by Cohere relevance (best first).

        Documents are ``title + snippet`` text; the response indexes back into
        the input list, so every original key (url, source, ...) survives.
        """
        documents = [
            f"{r.get('title', '')}\n{r.get('snippet', '')}".strip()
            or str(r.get("url", ""))
            for r in results
        ]
        body: dict[str, object] = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": min(max(top_n, 1), len(documents)),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/v2/rerank",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Accept": "application/json",
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(f"cohere rerank HTTP {resp.status_code}")
        ranked: list[dict] = []
        for hit in resp.json().get("results") or []:
            idx = hit.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(results)):
                continue
            item = dict(results[idx])
            item["rerank_score"] = round(float(hit.get("relevance_score", 0.0)), 4)
            ranked.append(item)
        return ranked


def reranker_from_env() -> CohereReranker | None:
    """Build the reranker when the double opt-in is satisfied, else ``None``."""
    if not settings.wet_search_rerank:
        return None
    if not settings.cohere_api_key:
        return None
    return CohereReranker(
        settings.cohere_api_key,
        model=settings.cohere_rerank_model or "rerank-v4.0-fast",
        base_url=settings.cohere_base_url or "https://api.cohere.com",
    )


async def maybe_rerank(query: str, data: dict, max_results: int) -> dict:
    """Reorder a successful chain envelope when rerank is enabled.

    Skips error envelopes and result sets with fewer than 2 items; any failure
    keeps the original envelope (search must never break because rerank did).
    """
    if data.get("error"):
        return data
    results = data.get("results")
    if not isinstance(results, list) or len(results) < 2:
        return data
    reranker = reranker_from_env()
    if reranker is None:
        return data
    try:
        ranked = await reranker.rerank(query, results, top_n=max_results)
    except Exception as exc:
        logger.warning(
            f"cohere rerank failed ({type(exc).__name__}); keeping original order"
        )
        return data
    if not ranked:
        return data
    out = dict(data)
    out["results"] = ranked
    out["reranked_by"] = "cohere"
    return out
