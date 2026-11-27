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


_STEERABLE_STATUSES = ("pending", "running")
# Most steering calls one job records; later ones are refused.
MAX_STEERING_ENTRIES = 50


def _steering_entries(params: dict[str, Any]) -> list[dict[str, Any]]:
    entries = params.get("steering")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _fold_steering(direction: Any, entries: list[dict[str, Any]]) -> Any:
    """Apply each entry's changes to ``direction`` in order (invalid ones skipped)."""
    from wet.sources.agent_orchestrator import apply_steering, validate_steering

    for entry in entries:
        changes, _ = validate_steering(entry.get("changes"))
        if changes is not None:
            direction = apply_steering(direction, changes)
    return direction


def _begin_run(db: Any, *, job_id: str, sub: str) -> Any:
    """Start a (re)run: rebuild the direction from steering already applied.

    Progress and the live direction of an earlier run are dropped, since the
    run starts over from the first search round. Steering still pending is
    left for the first checkpoint. Only then is the job marked running, so a
    steer call never sees a running job with an earlier run's progress (a
    stale "synthesize" would refuse it).
    """
    from wet.sources.agent_orchestrator import ResearchDirection

    state: dict[str, Any] = {}

    def _mutate(row: dict, params: dict) -> dict | None:
        applied = [
            entry
            for entry in _steering_entries(params)
            if entry.get("applied_at") is not None
        ]
        state["direction"] = _fold_steering(ResearchDirection(), applied)
        if "progress" not in params and "direction" not in params:
            return None
        params.pop("progress", None)
        params.pop("direction", None)
        return params

    db.update_job_params(job_id, sub=sub, mutate=_mutate)
    db.update_job(job_id, sub=sub, status="running")
    return state.get("direction") or ResearchDirection()


def _checkpoint(
    db: Any,
    *,
    job_id: str,
    sub: str,
    step: str,
    round_no: int,
    direction: Any,
    decide: Any = None,
) -> Any:
    """Apply pending steering at an orchestration checkpoint.

    Pending entries are applied in order and stamped with the step and round
    they took effect at; that step becomes the job's progress. Where the
    next step depends on the direction (``decide`` is set), it is the step
    the steered direction leads to. One write transaction covers all of it,
    so a concurrent ``steer`` call lands either before (applied now) or
    after (applied at the next checkpoint). Returns None when another
    process marked the job cancelled, else the direction to continue with.
    """
    state: dict[str, Any] = {"direction": direction}

    def _mutate(row: dict, params: dict) -> dict | None:
        if row["status"] == "cancelled":
            state["cancelled"] = True
            return None
        now = _now_ts()
        pending = [
            entry
            for entry in _steering_entries(params)
            if entry.get("applied_at") is None
        ]
        current = _fold_steering(direction, pending)
        at_step, at_round = decide(current) if decide else (step, round_no)
        for entry in pending:
            entry.update(applied_at=now, applied_step=at_step, applied_round=at_round)
        params["progress"] = {"step": at_step, "round": at_round, "at": now}
        params["direction"] = current.to_dict()
        state["direction"] = current
        return params

    db.update_job_params(job_id, sub=sub, mutate=_mutate)
    if state.get("cancelled"):
        return None
    return state["direction"]


def steer_research_job(
    db: Any, *, job_id: str, changes: Any, sub: str = "default"
) -> dict[str, Any]:
    """Record a steering change for a pending or running research job.

    The change is validated now and applied at the job's next orchestration
    checkpoint (before its next search, extraction or synthesis). Once the
    job has started synthesising its answer, steering is refused, as is a
    steer past :data:`MAX_STEERING_ENTRIES` calls or one that would push a
    direction list past ``MAX_DIRECTION_ITEMS`` entries.
    """
    from wet.sources.agent_orchestrator import (
        STEP_SYNTHESIZE,
        ResearchDirection,
        steering_limit_error,
        validate_steering,
    )

    outcome: dict[str, Any] = {}

    def _mutate(row: dict, params: dict) -> dict | None:
        status = row["status"]
        if status not in _STEERABLE_STATUSES:
            outcome["error"] = (
                f"Error: Research job '{job_id}' is {status}; only pending or "
                "running jobs can be steered."
            )
            return None
        normalized, error = validate_steering(changes)
        if normalized is None:
            outcome["error"] = error
            return None
        progress = params.get("progress")
        if isinstance(progress, dict) and progress.get("step") == STEP_SYNTHESIZE:
            outcome["error"] = (
                f"Error: Research job '{job_id}' is already synthesising its "
                "answer; steering applies only before synthesis."
            )
            return None
        entries = _steering_entries(params)
        if len(entries) >= MAX_STEERING_ENTRIES:
            outcome["error"] = (
                f"Error: Research job '{job_id}' already has "
                f"{MAX_STEERING_ENTRIES} steering changes, the most one job "
                "accepts; start a new job to change direction again."
            )
            return None
        limit_error = steering_limit_error(
            _fold_steering(ResearchDirection(), entries), normalized
        )
        if limit_error is not None:
            outcome["error"] = limit_error
            return None
        last_seq = max(
            (entry["seq"] for entry in entries if isinstance(entry.get("seq"), int)),
            default=0,
        )
        entry = {
            "seq": last_seq + 1,
            "at": _now_ts(),
            "changes": normalized,
            "applied_at": None,
            "applied_step": None,
            "applied_round": None,
        }
        params["steering"] = [*entries, entry]
        outcome.update(status=status, entry=entry)
        return params

    row = db.update_job_params(job_id, sub=sub, mutate=_mutate)
    if row is None:
        return {"error": f"Error: Research job '{job_id}' not found."}
    if "error" in outcome:
        return {"error": outcome["error"]}
    return {"job_id": job_id, "status": outcome["status"], "steer": outcome["entry"]}


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

    async def _on_step(step: str, round_no: int, direction: Any, decide: Any) -> Any:
        current = await asyncio.to_thread(
            _checkpoint,
            db,
            job_id=job_id,
            sub=sub,
            step=step,
            round_no=round_no,
            direction=direction,
            decide=decide,
        )
        if current is None:
            raise asyncio.CancelledError
        return current

    # The job is marked running, without the earlier run's progress, before
    # start or resume returns, so a caller sees the restart at once. This
    # stays synchronous: an await here would let a second resume slip in
    # before the task is registered.
    direction = _begin_run(db, job_id=job_id, sub=sub)

    async def _runner() -> None:
        try:
            outcome = await run_agent(
                query=query,
                max_urls=max_urls,
                synthesis_model=synthesis_model,
                token_budget=token_budget,
                direction=direction,
                on_step=_on_step,
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
    out.update(_steering_status(row.get("params_json")))
    return out


def _steering_status(params_json: str | None) -> dict[str, Any]:
    """Progress, steering log and effective direction for job status.

    The direction is the one the run last used with any still-pending
    steering applied on top, i.e. where the job will head next.
    """
    from wet.sources.agent_orchestrator import ResearchDirection

    try:
        params = json.loads(params_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(params, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(params.get("progress"), dict):
        out["progress"] = params["progress"]
    entries = _steering_entries(params)
    if entries:
        stored = params.get("direction")
        if isinstance(stored, dict):
            base = ResearchDirection.from_dict(stored)
            pending = [e for e in entries if e.get("applied_at") is None]
        else:
            base, pending = ResearchDirection(), entries
        out["steering"] = entries
        out["direction"] = _fold_steering(base, pending).to_dict()
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
