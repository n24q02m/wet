"""Setup tool -- warmup logic as MCP-callable functions.

Extracted from __main__.py CLI commands into async functions that return
structured dicts for MCP tool responses.
"""

import asyncio
import inspect
import os
import shutil
from pathlib import Path

from loguru import logger

from wet_mcp.config import settings


def _resolve_cache_dir() -> Path:
    """Resolve the fastretrieval cache path."""
    explicit = os.getenv("FASTRETRIEVAL_CACHE_PATH")
    if explicit:
        return Path(explicit)

    xdg_cache_home = os.getenv("XDG_CACHE_HOME")
    base_path = Path(xdg_cache_home) if xdg_cache_home else Path.home() / ".cache"
    return base_path / "fastretrieval"


def clear_model_cache(model_name: str) -> str | None:
    """Remove corrupted HuggingFace cache for a model so it re-downloads.

    Returns the path that was cleared, or None if no cache existed.
    """
    cache_dir = _resolve_cache_dir()
    safe_name = model_name.replace("/", "--")
    model_cache = cache_dir / f"models--{safe_name}"
    if model_cache.exists():
        shutil.rmtree(model_cache)
        return str(model_cache)
    return None


async def _validate_cloud_models(settings_obj) -> dict:
    """Validate the per-task cloud cells ([models.embed] / [models.rerank]).

    Returns ``{"cloud_ready": False}`` when no cell is configured; a
    configured cell that fails its check is reported under ``errors``.
    """
    from wet_mcp.runtime import cell_configured, model_cell

    result: dict = {"cloud_ready": False}

    if cell_configured("embed"):
        cell = model_cell("embed")
        from wet_mcp.embedder import init_backend

        try:
            backend = init_backend("cloud", cell.model)
            dims = await backend.check_available()
            if dims > 0:
                result["embedding"] = {"model": cell.model, "dims": dims}
            else:
                result.setdefault("errors", []).append(
                    f"embed cell {cell.model}: check_available returned no dims"
                )
        except Exception as exc:
            logger.debug(f"Cloud embedding {cell.model} failed: {exc}")
            result.setdefault("errors", []).append(f"embed cell {cell.model}: {exc}")

    if cell_configured("rerank"):
        cell = model_cell("rerank")
        from wet_mcp.reranker import init_reranker

        try:
            reranker = init_reranker("cloud", cell.model)
            checked = reranker.check_available()
            if inspect.isawaitable(checked):
                checked = await checked
            if checked:
                result["reranker"] = {"model": cell.model}
            else:
                result.setdefault("errors", []).append(
                    f"rerank cell {cell.model}: check_available false"
                )
        except Exception as exc:
            logger.debug(f"Cloud reranker {cell.model} failed: {exc}")
            result.setdefault("errors", []).append(f"rerank cell {cell.model}: {exc}")

    if result.get("embedding") or result.get("reranker"):
        result["cloud_ready"] = True
    return result


def _download_local_embedding(settings_obj) -> dict:
    """Download and validate local embedding model."""
    from fastretrieval import TextEmbedding

    local_model = settings_obj.resolve_local_embedding_model()
    try:
        embed_model = TextEmbedding(model_name=local_model)
        result = list(embed_model.embed(["warmup test"]))
        if result:
            return {
                "step": "local_embedding",
                "status": "ok",
                "model": local_model,
                "dims": len(result[0]),
            }
        return {
            "step": "local_embedding",
            "status": "warning",
            "message": "Embedding test returned empty result",
        }
    except Exception as exc:
        if "NO_SUCHFILE" in str(exc) or "doesn't exist" in str(exc):
            cleared = clear_model_cache(local_model)
            logger.info(f"Cleared corrupted cache: {cleared}")
            embed_model = TextEmbedding(model_name=local_model)
            result = list(embed_model.embed(["warmup test"]))
            if result:
                return {
                    "step": "local_embedding",
                    "status": "ok",
                    "model": local_model,
                    "dims": len(result[0]),
                    "retried": True,
                }
            return {
                "step": "local_embedding",
                "status": "warning",
                "message": "Embedding test failed after cache clear",
            }
        raise


def _download_local_reranker(settings_obj) -> dict:
    """Download and validate local reranker model."""
    if not settings_obj.rerank_enabled:
        return {
            "step": "local_reranker",
            "status": "skipped",
            "message": "Reranking disabled",
        }

    from fastretrieval import TextCrossEncoder

    local_model = settings_obj.resolve_local_rerank_model()
    try:
        reranker = TextCrossEncoder(model_name=local_model)
        scores = list(reranker.rerank("test query", ["test document"]))
        if scores:
            return {
                "step": "local_reranker",
                "status": "ok",
                "model": local_model,
            }
        return {
            "step": "local_reranker",
            "status": "warning",
            "message": "Reranker test returned empty result",
        }
    except Exception as exc:
        if "NO_SUCHFILE" in str(exc) or "doesn't exist" in str(exc):
            cleared = clear_model_cache(local_model)
            logger.info(f"Cleared corrupted cache: {cleared}")
            reranker = TextCrossEncoder(model_name=local_model)
            scores = list(reranker.rerank("test query", ["test document"]))
            if scores:
                return {
                    "step": "local_reranker",
                    "status": "ok",
                    "model": local_model,
                    "retried": True,
                }
            return {
                "step": "local_reranker",
                "status": "warning",
                "message": "Reranker test failed after cache clear",
            }
        raise


async def _warmup_cloud_models(steps: list[dict]) -> dict | None:
    """Check the configured cloud cells and return early if any is ready."""
    from wet_mcp.runtime import cell_configured

    if not (cell_configured("embed") or cell_configured("rerank")):
        return None

    cloud_result = await _validate_cloud_models(settings)
    if cloud_result["cloud_ready"]:
        steps.append({"step": "cloud_models", "status": "ok"})
        return {
            "status": "ok",
            "mode": "cloud",
            "steps": steps,
            "embedding": cloud_result.get("embedding"),
            "reranker": cloud_result.get("reranker"),
        }

    steps.append(
        {
            "step": "cloud_models",
            "status": "fallback",
            "message": "Configured cloud cells unavailable, falling back to local",
        }
    )
    return None


async def run_warmup() -> dict:
    """Pre-download models and run setup to avoid first-run delays.

    Returns a structured dict with warmup results:
    {
        "status": "ok" | "error",
        "mode": "cloud" | "local",
        "steps": [{"step": str, "status": str, ...}, ...],
        "embedding": {...},  # if cloud
        "reranker": {...},   # if cloud reranker available
    }
    """
    steps = []

    # 1. Run auto-setup (SearXNG + Playwright)
    try:
        from wet_mcp.setup import run_auto_setup

        await asyncio.to_thread(run_auto_setup)
        steps.append({"step": "auto_setup", "status": "ok"})
    except Exception as exc:
        steps.append(
            {
                "step": "auto_setup",
                "status": "warning",
                "error": str(exc),
            }
        )

    # 2. Check cloud models if API keys are configured
    cloud_ready_result = await _warmup_cloud_models(steps)
    if cloud_ready_result:
        return cloud_ready_result

    # 3. Download local models
    embed_result = await asyncio.to_thread(_download_local_embedding, settings)
    steps.append(embed_result)

    reranker_result = await asyncio.to_thread(_download_local_reranker, settings)
    steps.append(reranker_result)

    return {
        "status": "ok",
        "mode": "local",
        "steps": steps,
    }
