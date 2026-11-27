#!/usr/bin/env python3
"""Reproducible W11 baseline benchmark runner for wet.

Spawns the real HTTP MCP server (``python -m wet.server``), measures cold/warm
startup latency and process RSS memory via ``psutil``, executes real protocol
calls (``search``, ``extract``, ``docs_query``) over streamable-HTTP
``ClientSession`` against the versioned ``v2`` benchmark fixtures, and
captures full ``pytest --cov=wet`` metrics into
``docs/benchmarks/v2_w11_baseline.json`` with zero ``null`` fields.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import psutil

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
SEARCH_QUALITY_DIR = TESTS_DIR / "search_quality"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "benchmarks" / "v2_w11_baseline.json"


def _ensure_sys_path() -> None:
    """Expose src/, tests/, and tests/search_quality/ for benchmark helpers."""
    for path_str in (str(REPO_ROOT / "src"), str(TESTS_DIR), str(SEARCH_QUALITY_DIR)):
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


# Isolated config matching tests/search_quality/run_contract.py (no cloud cells).
_BENCHMARK_CONFIG_TOML = """\
[server]
auth = "no-auth"

[models.embed]
base_url = "https://benchmark.invalid/v1"
model = "benchmark-disabled"

[models.rerank]
base_url = "https://benchmark.invalid/v1"
model = "benchmark-disabled"
"""

_PYTEST_SUMMARY_RE = re.compile(
    r"(?:(?P<failed>\d+)\s+failed,\s*)?"
    r"(?P<passed>\d+)\s+passed"
    r"(?:,\s*(?P<skipped>\d+)\s+skipped)?"
    r"(?:,\s*(?P<deselected>\d+)\s+deselected)?"
    r".*?\bin\s+(?P<duration>[0-9]+(?:\.[0-9]+)?)s"
)


def _select_search_backend(requested: str) -> str:
    """Resolve the direct web search backend chain for the live server."""
    if requested != "auto":
        return requested
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return "tavily"
    if os.environ.get("SEARXNG_URL", "").strip():
        return "searxng"
    return "keenable,firecrawl"


def _rmtree_retry(path: Path, attempts: int = 8, delay_s: float = 0.25) -> None:
    """Remove a directory tree, tolerating brief Windows handle release lag."""
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                shutil.rmtree(path, ignore_errors=True)
                return
            time.sleep(delay_s)


def _measure_process_rss_mb(supervisor_pid: int) -> float:
    """Sum RSS memory (MiB) across the supervised wet.server process tree."""
    try:
        parent = psutil.Process(supervisor_pid)
    except psutil.NoSuchProcess:
        return 0.0
    children = parent.children(recursive=True)
    targets = children if children else [parent]
    total_bytes = 0
    for proc in targets:
        try:
            total_bytes += proc.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return round(total_bytes / (1024 * 1024), 2)


def _seed_docs_db(
    db_path: Path,
    corpus: list[dict[str, Any]],
    *,
    embedding_dims: int,
    model_identity: str,
) -> None:
    """Materialize the versioned v2 docs corpus into an isolated SQLite DocsDB."""
    from wet.db import DocsDB

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in corpus:
        grouped[record["library"]].append(record)

    database = DocsDB(
        db_path, embedding_dims=embedding_dims, model_identity=model_identity
    )
    try:
        for library in sorted(grouped):
            records = grouped[library]
            library_id = database.upsert_library(
                name=library,
                canonical_name=library,
                docs_url=f"https://benchmark.invalid/library/{records[0]['id']}",
                registry="benchmark-v2",
                description="Controlled wet benchmark fixture",
            )
            version_id = database.upsert_version(
                library_id=library_id,
                version="benchmark-v2",
                docs_url=f"https://benchmark.invalid/library/{records[0]['id']}",
            )
            chunks = [
                {
                    "url": record["url"],
                    "title": record["title"],
                    "content": record["content"],
                    "heading_path": record["title"],
                    "chunk_index": index,
                    "topic": record["topic"],
                    "section": "benchmark-v2",
                    "token_count": max(1, len(record["content"].split())),
                }
                for index, record in enumerate(records)
            ]
            database.add_chunks(
                version_id=version_id,
                library_id=library_id,
                chunks=chunks,
            )
            database.mark_version_indexed(
                version_id,
                page_count=len(chunks),
                chunk_count=len(chunks),
            )
    finally:
        database.close()


def _build_server_env(
    temp_root: Path, docs_db_path: Path, search_backend: str
) -> tuple[dict[str, str], int, str]:
    """Build isolated server env and matching embedding identity."""
    _ensure_sys_path()
    from live_http import wet_server_env  # type: ignore[import-not-found]

    from wet.runtime import DEFAULT_EMBEDDING_DIMS

    env = wet_server_env(temp_root)
    env.update(
        {
            "CACHE_DIR": str(temp_root / "cache"),
            "DOCS_DB_BACKEND": "sqlite",
            "DOCS_DB_PATH": str(docs_db_path),
            "WET_DOCS_DB_PATH": str(docs_db_path),
            "DOWNLOAD_DIR": str(temp_root / "downloads"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "WARNING"),
            "SEARCH_BACKENDS": search_backend,
            "DISABLE_LOCAL_EMBED": "true",
            "DISABLE_LOCAL_RERANK": "true",
            "EMBEDDING_DIMS": "768",
            "LOCAL_EMBEDDING_MODEL": "n24q02m/Qwen3-Embedding-0.6B-ONNX",
            "REINDEX_ON_MODEL_CHANGE": "false",
        }
    )
    if "duckduckgo" in search_backend or "startpage" in search_backend:
        env["WET_ALLOW_SERP_SCRAPE"] = "true"

    home = Path(env["HOME"])
    config_dir = home / ".n24q02m" / "wet"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(_BENCHMARK_CONFIG_TOML, encoding="utf-8")

    dims = int(env.get("EMBEDDING_DIMS") or "0") or DEFAULT_EMBEDDING_DIMS
    model = env.get("LOCAL_EMBEDDING_MODEL") or "n24q02m/Qwen3-Embedding-0.6B-ONNX"
    return env, dims, model


async def _run_bounded(
    cases: list[dict[str, Any]],
    runner: Any,
    *,
    concurrency: int,
) -> tuple[list[dict[str, Any]], float]:
    """Run async benchmark cases with bounded concurrency and return (records, wall_s)."""
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict[str, Any] | None] = [None] * len(cases)
    started = time.perf_counter()

    async def _one(idx: int, case: dict[str, Any]) -> None:
        async with sem:
            results[idx] = await runner(case)

    async with asyncio.TaskGroup() as group:
        for idx, case in enumerate(cases):
            group.create_task(_one(idx, case))

    elapsed_s = max(time.perf_counter() - started, 1e-6)
    return [r for r in results if r is not None], elapsed_s


async def _run_live_suites(
    *,
    search_backend: str,
    extract_limit: int,
    web_limit: int,
    docs_limit: int,
    extract_concurrency: int,
    web_concurrency: int,
    docs_concurrency: int,
) -> dict[str, Any]:
    """Spawn wet.server and run startup, RSS, extract, web search, and docs recall."""
    _ensure_sys_path()
    import benchmark_contract as contract  # type: ignore[import-not-found]
    from live_http import (  # type: ignore[import-not-found]
        mcp_client_session,
        spawn_wet_server,
        wait_until_up,
    )
    from process_lifeline import stop_supervised  # type: ignore[import-not-found]

    fixture_root = contract.DEFAULT_FIXTURE_ROOT
    docs_corpus = contract.load_jsonl(
        fixture_root / contract.FIXTURE_FILES["docs_corpus"]
    )
    docs_cases = contract.load_jsonl(
        fixture_root / contract.FIXTURE_FILES["docs_recall_cases"]
    )[:docs_limit]
    extract_cases = contract.load_jsonl(
        fixture_root / contract.FIXTURE_FILES["extract_urls"]
    )[:extract_limit]
    web_cases = contract.load_jsonl(
        fixture_root / contract.FIXTURE_FILES["web_search_queries"]
    )[:web_limit]

    temp_root = Path(tempfile.mkdtemp(prefix="wet-w11-baseline-"))
    try:
        docs_db_path = temp_root / "docs.db"
        env, dims, model_identity = _build_server_env(
            temp_root, docs_db_path, search_backend
        )
        _seed_docs_db(
            docs_db_path,
            docs_corpus,
            embedding_dims=dims,
            model_identity=model_identity,
        )

        log_path = temp_root / "server.log"
        spawn_t0 = time.perf_counter()
        proc = spawn_wet_server(env, log_path)
        port = int(env["WET_PORT"])
        try:
            wait_until_up(proc, port, log_path, timeout=90.0)
            http_ready_ms = (time.perf_counter() - spawn_t0) * 1000.0
            async with mcp_client_session(port, timeout=120.0) as session:
                await session.list_tools()
                startup_time_ms = round((time.perf_counter() - spawn_t0) * 1000.0, 2)
                rss_idle_mb = _measure_process_rss_mb(proc.pid)

                docs_records, docs_wall_s = await _run_bounded(
                    docs_cases,
                    lambda c: contract.run_docs_case(session, c),
                    concurrency=docs_concurrency,
                )
                web_records, web_wall_s = await _run_bounded(
                    web_cases,
                    lambda c: contract.run_web_case(session, c),
                    concurrency=web_concurrency,
                )
                extract_records, extract_wall_s = await _run_bounded(
                    extract_cases,
                    lambda c: contract.run_extract_case(session, c),
                    concurrency=extract_concurrency,
                )

                rss_steady_mb = _measure_process_rss_mb(proc.pid)
        finally:
            stop_supervised(proc)
    finally:
        _rmtree_retry(temp_root)

    docs_summary = contract.summarize_suite("docs_recall", docs_records)
    web_summary = contract.summarize_suite("web_search", web_records)
    extract_summary = contract.summarize_suite("extract", extract_records)

    return {
        "process": {
            "http_ready_ms": round(http_ready_ms, 2),
            "startup_time_ms": startup_time_ms,
            "rss_idle_mb": rss_idle_mb,
            "rss_steady_mb": rss_steady_mb,
        },
        "docs_recall": {
            "case_count": docs_summary["case_count"],
            "wall_seconds": round(docs_wall_s, 2),
            "throughput_qps": round(docs_summary["case_count"] / docs_wall_s, 2),
            "metrics": {
                k: round(float(v), 4) for k, v in docs_summary["metrics"].items()
            },
        },
        "web_search": {
            "backend": search_backend,
            "case_count": web_summary["case_count"],
            "wall_seconds": round(web_wall_s, 2),
            "throughput_qps": round(web_summary["case_count"] / web_wall_s, 2),
            "metrics": {
                k: round(float(v), 4) for k, v in web_summary["metrics"].items()
            },
        },
        "extract": {
            "case_count": extract_summary["case_count"],
            "wall_seconds": round(extract_wall_s, 2),
            "throughput_urls_per_sec": round(
                extract_summary["case_count"] / extract_wall_s, 2
            ),
            "metrics": {
                k: round(float(v), 4) for k, v in extract_summary["metrics"].items()
            },
        },
        "corpus_counts": {
            "docs_corpus": len(docs_corpus),
            "docs_recall_cases": len(docs_cases),
            "web_search_queries": len(web_cases),
            "extract_urls": len(extract_cases),
        },
    }


_PYTEST_STRIP_ENV = frozenset(
    {
        "BRAVE_API_KEY",
        "CAPSOLVER_API_KEY",
        "CF_BROWSER_RENDERING_TOKEN",
        "CF_D1_ID",
        "CF_KV_ID",
        "CF_VECTORIZE_ID",
        "CI_APP_KEY",
        "CREDENTIAL_SECRET",
        "DISABLE_LOCAL_EMBED",
        "DISABLE_LOCAL_RERANK",
        "DOCKERHUB_TOKEN",
        "DOCKERHUB_USERNAME",
        "EXA_API_KEY",
        "FIRECRAWL_API_KEY",
        "KAGI_API_KEY",
        "MCP_DCR_SERVER_SECRET",
        "MCP_JWT_SIGNING_SECRET",
        "OPENROUTER_API_KEY",
        "PUBLIC_URL",
        "REINDEX_ON_MODEL_CHANGE",
        "SEARCH_BACKENDS",
        "SEARXNG_URL",
        "TAVILY_API_KEY",
    }
)


def _run_pytest_coverage() -> tuple[dict[str, Any], dict[str, Any]]:
    """Run full pytest with branch coverage and parse counts + coverage %."""
    clean_env = {
        key: value for key, value in os.environ.items() if key not in _PYTEST_STRIP_ENV
    }
    with tempfile.TemporaryDirectory(prefix="wet-cov-") as tmp_dir:
        cov_json = Path(tmp_dir) / "coverage.json"
        cmd = [
            "uv",
            "run",
            "pytest",
            "--cov=wet",
            f"--cov-report=json:{cov_json}",
            "--cov-fail-under=95",
            "--timeout=30",
        ]
        completed = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=clean_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        combined = completed.stdout + "\n" + completed.stderr
        if completed.returncode != 0:
            raise RuntimeError(
                f"pytest failed with exit code {completed.returncode}:\n{combined[-3000:]}"
            )
        match = _PYTEST_SUMMARY_RE.search(combined)
        if not match:
            raise RuntimeError(
                f"Could not parse pytest summary line from:\n{combined[-1500:]}"
            )
        cov_data = json.loads(cov_json.read_text(encoding="utf-8"))
        total_pct = round(float(cov_data["totals"]["percent_covered"]), 2)
        test_suite = {
            "passed": int(match.group("passed")),
            "skipped": int(match.group("skipped") or 0),
            "deselected": int(match.group("deselected") or 0),
            "duration_seconds": round(float(match.group("duration")), 2),
        }
        coverage = {
            "total_pct": total_pct,
            "fail_under_gate": 95,
            "long_term_target_pct": 95,
        }
        return test_suite, coverage


def _assert_no_nulls(value: Any, path: str = "$") -> None:
    """Fail if any field anywhere in the artifact is None (JSON null)."""
    if value is None:
        raise ValueError(f"Benchmark artifact contains null at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_nulls(item, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _assert_no_nulls(item, f"{path}[{idx}]")


def _git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible W11 baseline benchmark for wet."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--search-backend", default="auto")
    parser.add_argument("--extract-limit", type=int, default=50)
    parser.add_argument("--web-limit", type=int, default=50)
    parser.add_argument("--docs-limit", type=int, default=200)
    parser.add_argument("--extract-concurrency", type=int, default=6)
    parser.add_argument("--web-concurrency", type=int, default=2)
    parser.add_argument("--docs-concurrency", type=int, default=4)
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Requires --pytest-metrics JSON when pytest already ran separately.",
    )
    parser.add_argument(
        "--pytest-metrics",
        type=Path,
        default=None,
        help="Optional JSON file with pre-measured test_suite and coverage objects.",
    )
    args = parser.parse_args()

    search_backend = _select_search_backend(args.search_backend)
    print(f"Running W11 baseline live suites (search_backend={search_backend})...")
    live = asyncio.run(
        _run_live_suites(
            search_backend=search_backend,
            extract_limit=args.extract_limit,
            web_limit=args.web_limit,
            docs_limit=args.docs_limit,
            extract_concurrency=args.extract_concurrency,
            web_concurrency=args.web_concurrency,
            docs_concurrency=args.docs_concurrency,
        )
    )

    if args.pytest_metrics is not None:
        raw_pm = json.loads(args.pytest_metrics.read_text(encoding="utf-8"))
        test_suite = raw_pm["test_suite"]
        coverage = raw_pm["coverage"]
    elif args.skip_pytest:
        raise SystemExit("--skip-pytest requires --pytest-metrics so no field is null.")
    else:
        print("Running full pytest + branch coverage gate (>= 95%)...")
        test_suite, coverage = _run_pytest_coverage()

    try:
        pkg_version = version("n24q02m-wet")
    except PackageNotFoundError:
        pkg_version = "unknown"

    artifact: dict[str, Any] = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "git_head": _git_output("rev-parse", "HEAD"),
        "version": pkg_version,
        "phase": "w11-wave2-baseline",
        "supersedes": "docs/benchmarks/v1_phase2_baseline.json",
        "purpose": (
            "Real W11 Wave 2 baseline replacing all May 2026 null placeholders "
            "via live MCP streamable-HTTP protocol calls and branch coverage."
        ),
        "metrics": {
            "test_suite": test_suite,
            "coverage": coverage,
            "search_p95_ms": live["web_search"]["metrics"]["p95_latency_ms"],
            "extract_tier1_success_rate": round(
                live["extract"]["metrics"]["success_rate"], 4
            ),
            "docs_query_p95_ms": live["docs_recall"]["metrics"]["p95_latency_ms"],
            "docs_query_recall_at_10": live["docs_recall"]["metrics"]["recall_at_10"],
            "startup_time_ms": live["process"]["startup_time_ms"],
            "rss_steady_mb": live["process"]["rss_steady_mb"],
        },
        "details": {
            "process": live["process"],
            "web_search": live["web_search"],
            "extract": live["extract"],
            "docs_recall": live["docs_recall"],
        },
        "corpus_sizes": live["corpus_counts"],
        "environment": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "search_backend": search_backend,
        },
        "reproduce_command": (
            "skret run -e prod -- uv run python scripts/run_w11_baseline.py"
        ),
    }

    _assert_no_nulls(artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} cleanly with zero null values.")
    print(json.dumps(artifact["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
