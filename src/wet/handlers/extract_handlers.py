"""Extract lifecycle handlers: monitor, async research jobs, semantic diff (WET-17, WET-46, WET-48, WET-49)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from wet.sources.agent_jobs import (
    cancel_research_job,
    get_research_job,
    resume_research_job,
    start_research_job,
)
from wet.sources.monitor import classify_change, content_digest


def build_semantic_diff_result(
    url: str,
    snapshots: list[dict[str, Any]],
    *,
    legacy_builder: Callable[[str, list[dict[str, Any]]], dict[str, Any]],
) -> dict[str, Any]:
    """Enrich diff results with deterministic noise filtering (WET-49) while preserving status keys."""
    base = legacy_builder(url, snapshots)
    if base.get("change_status") != "changed" or len(snapshots) < 2:
        return base
    old_content = str(snapshots[1].get("content") or "")
    new_content = str(snapshots[0].get("content") or "")
    classified = classify_change(old_content, new_content, url=url)
    if classified["change_status"] == "noise_only":
        return {
            "url": url,
            "change_status": "same",
            "semantic_status": "noise_only",
            "noise_lines_filtered": classified["noise_lines_filtered"],
            "change_ratio": 0.0,
            "diff": "",
            "old_fetched_at": base.get("old_fetched_at"),
            "new_fetched_at": base.get("new_fetched_at"),
        }
    return {
        **base,
        "semantic_status": "meaningful",
        "change_ratio": classified["change_ratio"],
        "noise_lines_filtered": classified["noise_lines_filtered"],
    }


async def _fetch_markdown_for_url(
    url: str,
    *,
    extract_fn: Callable[..., Awaitable[str]],
    format: str = "markdown",
    stealth: bool = False,
) -> tuple[str | None, str | None]:
    raw = await extract_fn(urls=[url], format=format, stealth=stealth)
    if isinstance(raw, str) and raw.startswith("Error"):
        return None, raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None, f"Error: invalid extract response for {url}"
    item = parsed[0] if isinstance(parsed, list) and parsed else parsed
    if not isinstance(item, dict):
        return None, f"Error: empty extract response for {url}"
    if item.get("error"):
        return None, str(item["error"])
    body = str(
        item.get("markdown") or item.get("clean_text") or item.get("content") or ""
    )
    return body, None


async def handle_monitor(
    *,
    docs_db: Any,
    monitor_op: str = "list",
    url: str | None = None,
    urls: list[str] | None = None,
    interval_seconds: int = 3600,
    sub: str = "default",
    extract_fn: Callable[..., Awaitable[str]] | None = None,
    format: str = "markdown",
    stealth: bool = False,
) -> dict[str, Any]:
    """Manage URL change watches (`watch` | `list` | `unwatch` | `check`)."""
    if docs_db is None:
        return {"error": "Error: Docs database not initialized"}

    op = (monitor_op or "list").strip().lower()
    target_url = url or (urls[0] if urls else None)

    if op == "watch":
        if not target_url:
            return {"error": "Error: url or urls[0] is required for monitor watch."}
        initial_content = ""
        initial_hash = ""
        checked_at: float | None = None
        if extract_fn is not None:
            body, err = await _fetch_markdown_for_url(
                target_url, extract_fn=extract_fn, format=format, stealth=stealth
            )
            if err:
                return {"url": target_url, "error": err}
            initial_content = body or ""
            initial_hash = content_digest(initial_content)
            import time

            checked_at = time.time()
        watch = await asyncio.to_thread(
            docs_db.upsert_watch,
            watch_id=f"watch_{uuid.uuid4().hex[:12]}",
            sub=sub,
            url=target_url,
            interval_seconds=max(60, int(interval_seconds)),
            last_content=initial_content,
            last_hash=initial_hash,
            last_checked_at=checked_at,
        )
        return {"action": "watch", "watch": watch}

    if op == "list":
        watches = await asyncio.to_thread(docs_db.list_watches, sub=sub)
        alerts = await asyncio.to_thread(docs_db.list_alerts, sub=sub, limit=20)
        return {"action": "list", "watches": watches, "alerts": alerts}

    if op == "unwatch":
        if not target_url:
            return {"error": "Error: url or urls[0] is required for monitor unwatch."}
        deleted = await asyncio.to_thread(docs_db.delete_watch, target_url, sub=sub)
        return {"action": "unwatch", "url": target_url, "removed": deleted}

    if op == "check":
        watches = (
            [w]
            if target_url
            and (w := await asyncio.to_thread(docs_db.get_watch, target_url, sub=sub))
            else await asyncio.to_thread(docs_db.list_watches, sub=sub)
        )
        if not watches:
            return {"action": "check", "checked": 0, "results": []}
        if extract_fn is None:
            return {"error": "Error: extractor unavailable for monitor check."}
        import time

        results: list[dict[str, Any]] = []
        for watch in watches:
            w_url = watch["url"]
            body, err = await _fetch_markdown_for_url(
                w_url, extract_fn=extract_fn, format=format, stealth=stealth
            )
            if err:
                results.append({"watch_id": watch["id"], "url": w_url, "error": err})
                continue
            new_body = body or ""
            old_body = str(watch.get("last_content") or "")
            classified = classify_change(old_body, new_body, url=w_url)
            new_hash = content_digest(new_body)
            now = time.time()
            await asyncio.to_thread(
                docs_db.upsert_watch,
                watch_id=watch["id"],
                sub=sub,
                url=w_url,
                interval_seconds=int(watch.get("interval_seconds") or 3600),
                last_content=new_body,
                last_hash=new_hash,
                last_checked_at=now,
            )
            alert_row: dict[str, Any] | None = None
            if classified["meaningful"]:
                alert_row = await asyncio.to_thread(
                    docs_db.record_alert,
                    alert_id=f"alert_{uuid.uuid4().hex[:12]}",
                    watch_id=watch["id"],
                    sub=sub,
                    url=w_url,
                    change_status=classified["change_status"],
                    change_ratio=classified["change_ratio"],
                    summary=f"Changed ({classified['change_ratio']:.1%})",
                    diff_text=classified["diff"],
                )
            results.append(
                {
                    "watch_id": watch["id"],
                    "url": w_url,
                    **classified,
                    **({"alert": alert_row} if alert_row is not None else {}),
                }
            )
        return {"action": "check", "checked": len(results), "results": results}

    return {
        "error": (
            f"Error: Unknown monitor operation '{monitor_op}'. "
            "Valid operations: watch, list, unwatch, check."
        )
    }


async def handle_async_agent(
    *,
    docs_db: Any,
    job_op: str,
    job_id: str | None = None,
    query: str | None = None,
    max_urls: int = 5,
    synthesis_model: str | None = None,
    token_budget: int = 10000,
    sub: str = "default",
) -> dict[str, Any]:
    """Dispatch async research job lifecycle operations (`start|status|resume|cancel`)."""
    if docs_db is None:
        return {"error": "Error: Docs database not initialized"}

    op = job_op.strip().lower()
    if op == "start":
        return await start_research_job(
            docs_db,
            query=query or "",
            max_urls=max_urls,
            synthesis_model=synthesis_model,
            token_budget=token_budget,
            sub=sub,
        )
    if op == "status":
        if not job_id:
            return {"error": "Error: job_id is required for agent status."}
        return await asyncio.to_thread(
            get_research_job, docs_db, job_id=job_id, sub=sub
        )
    if op == "resume":
        if not job_id:
            return {"error": "Error: job_id is required for agent resume."}
        return await resume_research_job(docs_db, job_id=job_id, sub=sub)
    if op == "cancel":
        if not job_id:
            return {"error": "Error: job_id is required for agent cancel."}
        return await asyncio.to_thread(
            cancel_research_job, docs_db, job_id=job_id, sub=sub
        )

    return {
        "error": (
            f"Error: Unknown async agent operation '{job_op}'. "
            "Valid operations: start, status, resume, cancel."
        )
    }
