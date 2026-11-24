"""Async research job lifecycle and deterministic citation verification (WET-46, WET-47)."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

from loguru import logger

# Keep active background tasks reachable so GC cannot cancel in-flight jobs.
_JOB_TASKS: dict[str, asyncio.Task[None]] = {}

_URL_RE = re.compile(r"https?://[^\s\])>\"']+")
_BRACKET_CITE_RE = re.compile(r"\[(\d+)\]")


def verify_citations(
    markdown: str,
    sources: list[dict[str, Any]],
    extracts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify markdown claims/citations against the stored extract evidence.

    Checks that every ``[N]`` citation index refers to a valid source and that
    every cited URL in the markdown matches an extracted source URL. Paragraphs
    making factual assertions without either a URL or ``[N]`` citation pointing
    to non-empty extract text are flagged under ``unverified_claims``.
    """
    by_index: dict[int, str] = {}
    evidence_by_url: dict[str, str] = {}

    for i, src in enumerate(sources):
        idx = int(src.get("index") or (i + 1))
        url = str(src.get("url") or "")
        if url:
            by_index[idx] = url

    for ext in extracts:
        url = str(ext.get("url") or "")
        body = ext.get("clean_text") or ext.get("markdown") or ext.get("content") or ""
        if url and not ext.get("error"):
            evidence_by_url[url] = body

    cited_indices = {int(m) for m in _BRACKET_CITE_RE.findall(markdown or "")}
    cited_urls = set(_URL_RE.findall(markdown or ""))

    valid_citations: list[dict[str, Any]] = []
    invalid_citations: list[str] = []

    for idx in sorted(cited_indices):
        target_url = by_index.get(idx)
        if target_url and target_url in evidence_by_url:
            valid_citations.append(
                {
                    "index": idx,
                    "url": target_url,
                    "evidence_chars": len(evidence_by_url[target_url]),
                }
            )
        else:
            invalid_citations.append(f"[{idx}]")

    for url in sorted(cited_urls):
        if url in evidence_by_url:
            if not any(v["url"] == url for v in valid_citations):
                valid_citations.append(
                    {
                        "url": url,
                        "evidence_chars": len(evidence_by_url[url]),
                    }
                )
        else:
            invalid_citations.append(url)

    unverified_claims: list[dict[str, str]] = []
    for raw_para in (markdown or "").split("\n\n"):
        para = raw_para.strip()
        if not para or para.startswith("#"):
            continue
        has_bracket = bool(_BRACKET_CITE_RE.search(para))
        has_url = bool(_URL_RE.search(para))
        if not has_bracket and not has_url and len(para) >= 30:
            unverified_claims.append(
                {
                    "flag": "unverified_claim",
                    "excerpt": para[:160],
                }
            )
        else:
            for m in _BRACKET_CITE_RE.findall(para):
                idx = int(m)
                if by_index.get(idx) not in evidence_by_url:
                    unverified_claims.append(
                        {
                            "flag": "unverified_claim",
                            "excerpt": para[:160],
                            "missing_citation": f"[{idx}]",
                        }
                    )

    return {
        "citations_verified": len(invalid_citations) == 0
        and len(unverified_claims) == 0,
        "verified_count": len(valid_citations),
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "unverified_claims": unverified_claims,
        "evidence_urls": sorted(evidence_by_url),
    }


def _now_ts() -> float:
    return time.time()


async def start_research_job(
    db: Any,
    *,
    query: str,
    max_urls: int = 5,
    synthesis_model: str | None = None,
    token_budget: int = 10000,
    sub: str = "default",
) -> dict[str, Any]:
    """Create a pending research job row and schedule asynchronous execution."""
    if not query or not query.strip():
        return {"error": "Error: query is required to start a research job."}

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    params = {
        "max_urls": max_urls,
        "synthesis_model": synthesis_model,
        "token_budget": token_budget,
    }
    db.create_job(
        job_id=job_id,
        sub=sub,
        kind="research",
        query=query,
        params_json=json.dumps(params),
    )
    _launch_job_task(
        db,
        job_id=job_id,
        sub=sub,
        query=query,
        max_urls=max_urls,
        synthesis_model=synthesis_model,
        token_budget=token_budget,
    )
    return {
        "job_id": job_id,
        "status": "running",
        "query": query,
    }


def _launch_job_task(
    db: Any,
    *,
    job_id: str,
    sub: str,
    query: str,
    max_urls: int,
    synthesis_model: str | None,
    token_budget: int,
) -> None:
    from wet.sources.agent_orchestrator import run_agent

    async def _runner() -> None:
        db.update_job(job_id, sub=sub, status="running")
        try:
            outcome = await run_agent(
                query=query,
                max_urls=max_urls,
                synthesis_model=synthesis_model,
                token_budget=token_budget,
            )
            if isinstance(outcome, str) and outcome.startswith("Error"):
                db.update_job(
                    job_id,
                    sub=sub,
                    status="failed",
                    error=outcome,
                    completed_at=_now_ts(),
                )
            else:
                payload = outcome if isinstance(outcome, dict) else {"result": outcome}
                db.update_job(
                    job_id,
                    sub=sub,
                    status="completed",
                    result_json=json.dumps(payload, ensure_ascii=False),
                    evidence_json=json.dumps(
                        payload.get("verification", {}), ensure_ascii=False
                    ),
                    completed_at=_now_ts(),
                )
        except asyncio.CancelledError:
            db.update_job(
                job_id,
                sub=sub,
                status="cancelled",
                error="Job cancelled by caller",
                completed_at=_now_ts(),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Research job {job_id} failed: {exc}")
            db.update_job(
                job_id,
                sub=sub,
                status="failed",
                error=str(exc),
                completed_at=_now_ts(),
            )
        finally:
            _JOB_TASKS.pop(job_id, None)

    task = asyncio.create_task(_runner(), name=f"wet-research-job-{job_id}")
    _JOB_TASKS[job_id] = task


def get_research_job(db: Any, *, job_id: str, sub: str = "default") -> dict[str, Any]:
    """Fetch current status and any completed output for ``job_id``."""
    row = db.get_job(job_id, sub=sub)
    if row is None:
        return {"error": f"Error: Research job '{job_id}' not found."}
    out: dict[str, Any] = {
        "job_id": row["id"],
        "status": row["status"],
        "query": row["query"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }
    if row.get("error"):
        out["error"] = row["error"]
    if row.get("result_json"):
        try:
            out["result"] = json.loads(row["result_json"])
        except json.JSONDecodeError:
            out["result"] = row["result_json"]
    return out


async def resume_research_job(
    db: Any, *, job_id: str, sub: str = "default"
) -> dict[str, Any]:
    """Resume a failed/cancelled/pending research job from stored parameters."""
    row = db.get_job(job_id, sub=sub)
    if row is None:
        return {"error": f"Error: Research job '{job_id}' not found."}
    if row["status"] == "completed" and row.get("result_json"):
        return get_research_job(db, job_id=job_id, sub=sub)
    if job_id in _JOB_TASKS and not _JOB_TASKS[job_id].done():
        return get_research_job(db, job_id=job_id, sub=sub)

    try:
        params = json.loads(row.get("params_json") or "{}")
    except json.JSONDecodeError:
        params = {}
    _launch_job_task(
        db,
        job_id=job_id,
        sub=sub,
        query=row["query"],
        max_urls=int(params.get("max_urls", 5)),
        synthesis_model=params.get("synthesis_model"),
        token_budget=int(params.get("token_budget", 10000)),
    )
    return {
        "job_id": job_id,
        "status": "running",
        "query": row["query"],
        "resumed": True,
    }


def cancel_research_job(
    db: Any, *, job_id: str, sub: str = "default"
) -> dict[str, Any]:
    """Cancel a queued or running research job."""
    row = db.get_job(job_id, sub=sub)
    if row is None:
        return {"error": f"Error: Research job '{job_id}' not found."}
    task = _JOB_TASKS.get(job_id)
    if task is not None and not task.done():
        task.cancel()
    db.update_job(
        job_id,
        sub=sub,
        status="cancelled",
        error="Job cancelled by caller",
        completed_at=_now_ts(),
    )
    return {"job_id": job_id, "status": "cancelled"}
