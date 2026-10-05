"""Measure wet's normal search quality through the MCP stdio protocol."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

DEFAULT_QUERY_FILE = Path(__file__).with_name("queries.jsonl")
MCP_COMMAND = ["uv", "run", "wet-mcp"]
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}
UNUSABLE_TEXT = re.compile(
    r"^(accept cookies?|cookies?|javascript required|enable javascript)", re.I
)
RANKING_K = 5
CAPTURE_QUERY_COUNT = 24
RANKING_METADATA_FIELDS = frozenset({"score"})
RerankCallable = Callable[
    [str, list[dict[str, Any]], int], Awaitable[list[dict[str, Any]]]
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_origin(url: str) -> str | None:
    if not url.strip():
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.hostname:
        return None
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    try:
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        return None
    return f"{parts.scheme.lower()}://{host.lower()}{port}"


def _rerank_models_provenance() -> list[str]:
    """Report the resolved reranker: [models.rerank] cell model, else local."""
    try:
        from wet.runtime import model_cell

        cell = model_cell("rerank")
        return [cell.model] if cell.configured else ["local"]
    except Exception:
        return ["unavailable"]


def _git_output(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def build_provenance(
    *,
    query_path: Path,
    command: list[str],
    execution_mode: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Describe the exact code, corpus, provider config, and invocation."""
    selected_env = os.environ if env is None else env
    search_backends = _csv(selected_env.get("SEARCH_BACKENDS", ""))
    if not search_backends:
        search_backends = [selected_env.get("SEARCH_BACKEND", "searxng").strip()]
    git_revision = _git_output("rev-parse", "HEAD")
    git_status = _git_output("status", "--porcelain")
    resolved_query_path = query_path.resolve()
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_mode": execution_mode,
        "code": {
            "git_revision": git_revision or "unavailable",
            "git_dirty": bool(git_status) if git_status is not None else None,
            "harness_sha256": _sha256_file(Path(__file__).resolve()),
        },
        "query_corpus": {
            "path": str(resolved_query_path),
            "sha256": _sha256_file(resolved_query_path),
        },
        "command": list(command),
        "mcp_command": MCP_COMMAND if execution_mode == "live_protocol" else None,
        "provider": {
            "search_backends": [backend.lower() for backend in search_backends],
            "searxng_origin": _safe_origin(selected_env.get("SEARXNG_URL", "")),
            "rerank_models": _rerank_models_provenance(),
        },
        "config": {
            "rerank_enabled": selected_env.get("RERANK_ENABLED", "true")
            .strip()
            .lower(),
            "rerank_top_n": selected_env.get("RERANK_TOP_N", "10").strip(),
            "disable_local_rerank": selected_env.get("DISABLE_LOCAL_RERANK", "false")
            .strip()
            .lower(),
        },
    }


def load_queries(path: Path) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        item = json.loads(line)
        required_strings = ("id", "query", "kind", "topic_group")
        if any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in required_strings
        ):
            raise ValueError(
                f"query line {line_number} needs non-empty id/query/kind/topic_group"
            )
        if item["id"] in seen_ids:
            raise ValueError(f"query line {line_number} has duplicate id {item['id']}")
        for key in ("topic_terms", "expected_domains"):
            values = item.get(key)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(
                    f"query line {line_number} needs a valid {key} string list"
                )
        if not item["topic_terms"]:
            raise ValueError(f"query line {line_number} needs topic_terms")
        min_topic_terms = item.get("min_topic_terms")
        if (
            type(min_topic_terms) is not int
            or min_topic_terms < 1
            or min_topic_terms > len(item["topic_terms"])
        ):
            raise ValueError(
                f"query line {line_number} needs min_topic_terms between 1 and "
                "the topic_terms count"
            )
        seen_ids.add(item["id"])
        queries.append(item)
    if not queries:
        raise ValueError(f"no queries found in {path}")
    return queries


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(query),
            "",
        )
    )


def _text(result: dict[str, Any]) -> str:
    return " ".join(
        str(result.get(key) or "") for key in ("title", "snippet", "content")
    ).strip()


def filter_unusable(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep results with a URL and useful human-readable text."""
    kept: list[dict[str, Any]] = []
    for result in results:
        url = str(result.get("url") or "").strip()
        text = _text(result)
        if not url or len(text) < 20 or UNUSABLE_TEXT.match(text):
            continue
        kept.append(result)
    return kept


def dedupe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by URL while preserving provider order."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for result in results:
        key = _canonical_url(str(result.get("url") or ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(result)
    return unique


def score_one(
    query_spec: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return the stable per-query quality schema used by baseline and after runs."""
    urls = [str(result.get("url") or "").strip() for result in results]
    domains = [urlsplit(url).netloc.lower() for url in urls if url]
    snippets = [str(result.get("snippet") or "").strip() for result in results]
    topic_terms = [str(term).lower() for term in query_spec.get("topic_terms", [])]
    min_topic_terms = int(query_spec.get("min_topic_terms", len(topic_terms) or 1))
    relevance: list[int] = []
    for result in results:
        haystack = _text(result).lower()
        matched_topic_terms = sum(term in haystack for term in set(topic_terms))
        topic_hit = matched_topic_terms >= min_topic_terms
        relevance.append(int(topic_hit))
    relevance_at_k = relevance[:RANKING_K]
    dcg_at_k = sum(
        relevant / math.log2(rank + 2) for rank, relevant in enumerate(relevance_at_k)
    )
    ideal_at_k = sorted(relevance, reverse=True)[:RANKING_K]
    ideal_dcg_at_k = sum(
        relevant / math.log2(rank + 2) for rank, relevant in enumerate(ideal_at_k)
    )
    canonical_urls = [_canonical_url(url) for url in urls if url]
    usable = filter_unusable(results)
    unique = dedupe(results)
    return {
        "id": query_spec["id"],
        "n_results": len(results),
        "usable_results": len(usable),
        "deduped_results": len(unique),
        "on_topic_hits": sum(relevance),
        "on_topic_hits_at_5": sum(relevance_at_k),
        "on_topic_ndcg_at_5": dcg_at_k / ideal_dcg_at_k if ideal_dcg_at_k else 0.0,
        "duplicate_ratio": 1 - (len(set(canonical_urls)) / len(canonical_urls))
        if canonical_urls
        else 0.0,
        "empty_snippet_ratio": sum(len(snippet) < 40 for snippet in snippets)
        / len(snippets)
        if snippets
        else 1.0,
        "unique_domains": len(set(domains)),
    }


def _payload(result: Any) -> dict[str, Any]:
    for attribute in ("structuredContent", "structured_content"):
        structured = getattr(result, attribute, None)
        if isinstance(structured, dict):
            return structured
    text = "".join(
        getattr(block, "text", "") for block in getattr(result, "content", [])
    )
    if not text:
        raise ValueError("MCP search returned no text content")
    wrapped = re.search(
        r"<untrusted_search_content>\s*(?P<payload>.*?)\s*</untrusted_search_content>",
        text,
        re.DOTALL,
    )
    if wrapped:
        text = wrapped.group("payload")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("MCP search payload is not an object")
    return data


def _server_env(temp_path: Path) -> dict[str, str]:
    """Build an isolated server environment for the search-quality protocol run."""
    env = {
        **os.environ,
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "WARNING"),
        "CACHE_DIR": str(temp_path / "cache"),
        "DOCS_DB_PATH": str(temp_path / "docs.db"),
        "DOWNLOAD_DIR": str(temp_path / "downloads"),
        # Search quality exercises the web-search path, not legacy Drive sync.
        # Blank both values so a stale one-sided local credential cannot prevent
        # server startup after the Drive-to-Cloudflare cutover.
        "GOOGLE_DRIVE_CLIENT_ID": "",
        "GOOGLE_DRIVE_CLIENT_SECRET": "",
    }
    return env


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_identity(result: dict[str, Any]) -> dict[str, Any]:
    """Return candidate payload fields that identify the captured document."""
    return {
        key: value
        for key, value in result.items()
        if key not in RANKING_METADATA_FIELDS
    }


def _candidate_identity_key(result: dict[str, Any]) -> str:
    return json.dumps(
        _candidate_identity(result),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _candidate_set_sha256(results: list[dict[str, Any]]) -> str:
    """Hash document identities as a multiset, excluding mutable rank scores."""
    canonical_candidates = sorted(_candidate_identity_key(result) for result in results)
    return _canonical_sha256(canonical_candidates)


def _candidate_order(results: list[dict[str, Any]]) -> list[str]:
    return [_candidate_identity_key(result) for result in results]


def _complete_reranked_candidates(
    captured: list[dict[str, Any]], reranked: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append candidates omitted by top-n reranking while preserving multiplicity."""
    remaining = list(captured)
    completed: list[dict[str, Any]] = []
    for result in reranked:
        identity = _candidate_identity_key(result)
        match_index = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if _candidate_identity_key(candidate) == identity
            ),
            None,
        )
        if match_index is None:
            raise RuntimeError("production reranker returned an unknown candidate")
        remaining.pop(match_index)
        completed.append(result)
    completed.extend(remaining)
    if _candidate_set_sha256(completed) != _candidate_set_sha256(captured):
        raise RuntimeError("production reranker changed the captured candidate set")
    return completed


def _artifact_records(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_records = artifact.get("queries")
    if not isinstance(raw_records, list):
        raise ValueError("artifact queries must be a list")
    records: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict) or not isinstance(record.get("query"), dict):
            raise ValueError(f"artifact query record {index} is invalid")
        query_id = record["query"].get("id")
        if not isinstance(query_id, str) or not query_id:
            raise ValueError(f"artifact query record {index} needs a query id")
        if query_id in records:
            raise ValueError(f"artifact has duplicate query id {query_id}")
        results = record.get("results")
        if not isinstance(results, list) or any(
            not isinstance(result, dict) for result in results
        ):
            raise ValueError(f"artifact results for query {query_id} must be objects")
        records[query_id] = record
    return records


def _build_report(
    records: list[dict[str, Any]],
    *,
    runner_error: str | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    scores = [record["score"] for record in records]

    def numeric(key: str) -> list[float]:
        return [score[key] for score in scores if score[key] is not None]

    def avg(key: str) -> float | None:
        values = numeric(key)
        return sum(values) / len(values) if values else None

    return {
        "schema_version": 2,
        "provenance": provenance,
        "query_file_schema": (
            "id/query/kind/topic_group/topic_terms/min_topic_terms/expected_domains"
        ),
        "n_queries": len(records),
        "n_errors": sum("error" in record for record in records),
        "runner_error": runner_error,
        "aggregate": {
            "avg_on_topic_hits": avg("on_topic_hits"),
            "avg_on_topic_hits_at_5": avg("on_topic_hits_at_5"),
            "avg_on_topic_ndcg_at_5": avg("on_topic_ndcg_at_5"),
            "avg_duplicate_ratio": avg("duplicate_ratio"),
            "avg_empty_snippet_ratio": avg("empty_snippet_ratio"),
            "avg_unique_domains": avg("unique_domains"),
            "total_results": sum(score["n_results"] for score in scores),
            "total_usable_results": sum(score["usable_results"] for score in scores),
            "total_deduped_results": sum(score["deduped_results"] for score in scores),
        },
        "queries": records,
    }


def replay_artifact(
    captured: dict[str, Any],
    queries: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Rescore captured candidates without invoking a provider or MCP server."""
    source_records = _artifact_records(captured)
    records: list[dict[str, Any]] = []
    for query_spec in queries:
        query_id = query_spec["id"]
        if query_id not in source_records:
            raise ValueError(f"artifact is missing query {query_id}")
        source_record = source_records[query_id]
        results = source_record["results"]
        record = {
            "query": query_spec,
            "score": score_one(query_spec, results),
            "results": results,
        }
        if "error" in source_record:
            record["capture_error"] = source_record["error"]
        records.append(record)
    report = _build_report(records, runner_error=None, provenance=provenance)
    report["replay_source_sha256"] = _canonical_sha256(captured)
    return report


async def _load_production_reranker() -> tuple[RerankCallable, dict[str, str]]:
    """Initialize and return wet's real configured production rerank path."""
    from wet import server
    from wet.reranker import resolve_rerank_backend_for_request

    await server._init_reranker_backend()
    backend = resolve_rerank_backend_for_request()
    if backend is None:
        raise RuntimeError(
            "production reranker is unavailable for the current configuration"
        )
    model = getattr(backend, "model", None) or getattr(
        backend, "_model_name", "unavailable"
    )

    async def production_rerank(
        query: str, results: list[dict[str, Any]], top_n: int
    ) -> list[dict[str, Any]]:
        # wet.server._rerank_results returns (ranked, jev_gate); the replay
        # contract measures ranking only, so the gate side-channel is dropped.
        ranked, _gate = await server._rerank_results(query, results, top_n)
        return ranked

    return production_rerank, {
        "callable": "wet.server._rerank_results",
        "backend_class": type(backend).__name__,
        "model": str(model),
        "provider_mode": "configured",
    }


async def replay_rerank_artifact(
    captured: dict[str, Any],
    queries: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Apply production reranking to one complete captured query artifact."""
    source_records = _artifact_records(captured)
    if (
        len(queries) != CAPTURE_QUERY_COUNT
        or len(source_records) != CAPTURE_QUERY_COUNT
    ):
        raise ValueError(
            f"replay-rerank requires exactly {CAPTURE_QUERY_COUNT} query records"
        )
    expected_ids = {query["id"] for query in queries}
    source_ids = set(source_records)
    if source_ids != expected_ids:
        missing = sorted(expected_ids - source_ids)
        unexpected = sorted(source_ids - expected_ids)
        raise ValueError(
            "replay-rerank query ids differ from the corpus "
            f"(missing={missing}, unexpected={unexpected})"
        )
    if captured.get("runner_error"):
        raise ValueError("replay-rerank source artifact has a runner error")
    for query_id, record in source_records.items():
        if "error" in record:
            raise ValueError(f"replay-rerank source query {query_id} has an error")
        if len(record["results"]) < 2:
            raise ValueError(
                f"replay-rerank source query {query_id} needs at least 2 candidates"
            )

    rerank_fn, runtime = await _load_production_reranker()
    records: list[dict[str, Any]] = []
    changed_query_orders = 0
    for query_spec in queries:
        source_results = source_records[query_spec["id"]]["results"]
        # Production deliberately bypasses when len(results) <= top_n. Request
        # n-1 ranked items, then append the one omitted captured candidate.
        rerank_top_n = len(source_results) - 1
        ranked_results = await rerank_fn(
            query_spec["query"], source_results, rerank_top_n
        )
        if not isinstance(ranked_results, list) or any(
            not isinstance(result, dict) for result in ranked_results
        ):
            raise RuntimeError("production reranker returned invalid candidates")
        completed_results = _complete_reranked_candidates(
            source_results, ranked_results
        )
        order_changed = _candidate_order(completed_results) != _candidate_order(
            source_results
        )
        changed_query_orders += int(order_changed)
        records.append(
            {
                "query": query_spec,
                "score": score_one(query_spec, completed_results),
                "results": completed_results,
                "rerank": {
                    "top_n": rerank_top_n,
                    "order_changed": order_changed,
                    "candidate_set_sha256": _candidate_set_sha256(source_results),
                },
            }
        )

    replay_provenance = {**provenance, "rerank_runtime": runtime}
    report = _build_report(
        records,
        runner_error=None,
        provenance=replay_provenance,
    )
    report["rerank_replay"] = {
        "source_artifact_sha256": _canonical_sha256(captured),
        "candidate_identity_excludes": sorted(RANKING_METADATA_FIELDS),
        "top_n_policy": "candidate_count_minus_one_then_append_omitted",
        "same_candidate_sets": True,
        "changed_query_orders": changed_query_orders,
    }
    return report


def compare_artifacts(
    before: dict[str, Any],
    after: dict[str, Any],
    queries: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Compare rank order only after proving each query has the same candidates."""
    before_records = _artifact_records(before)
    after_records = _artifact_records(after)
    comparison_records: list[dict[str, Any]] = []
    for query_spec in queries:
        query_id = query_spec["id"]
        if query_id not in before_records:
            raise ValueError(f"before artifact is missing query {query_id}")
        if query_id not in after_records:
            raise ValueError(f"after artifact is missing query {query_id}")
        before_results = before_records[query_id]["results"]
        after_results = after_records[query_id]["results"]
        before_fingerprint = _candidate_set_sha256(before_results)
        after_fingerprint = _candidate_set_sha256(after_results)
        if before_fingerprint != after_fingerprint:
            raise ValueError(f"candidate set differs for query {query_id}")
        before_score = score_one(query_spec, before_results)
        after_score = score_one(query_spec, after_results)
        comparison_records.append(
            {
                "id": query_id,
                "same_candidate_set": True,
                "candidate_set_sha256": before_fingerprint,
                "before": before_score,
                "after": after_score,
                "delta": {
                    "on_topic_hits": (
                        after_score["on_topic_hits"] - before_score["on_topic_hits"]
                    ),
                    "on_topic_hits_at_5": (
                        after_score["on_topic_hits_at_5"]
                        - before_score["on_topic_hits_at_5"]
                    ),
                    "on_topic_ndcg_at_5": (
                        after_score["on_topic_ndcg_at_5"]
                        - before_score["on_topic_ndcg_at_5"]
                    ),
                },
            }
        )

    def average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "schema_version": 2,
        "provenance": provenance,
        "source_artifacts": {
            "before_sha256": _canonical_sha256(before),
            "after_sha256": _canonical_sha256(after),
        },
        "candidate_identity_excludes": sorted(RANKING_METADATA_FIELDS),
        "n_queries": len(comparison_records),
        "aggregate": {
            "avg_on_topic_hits_at_5_delta": average(
                [record["delta"]["on_topic_hits_at_5"] for record in comparison_records]
            ),
            "avg_on_topic_ndcg_at_5_delta": average(
                [record["delta"]["on_topic_ndcg_at_5"] for record in comparison_records]
            ),
        },
        "queries": comparison_records,
    }


def _load_artifact(path: Path) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict):
        raise ValueError(f"artifact {path} must contain a JSON object")
    return artifact


async def run(
    queries: list[dict[str, Any]], *, provenance: dict[str, Any]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    runner_error: str | None = None
    with tempfile.TemporaryDirectory(prefix="wet-search-quality-") as temp_dir:
        temp_path = Path(temp_dir)
        env = _server_env(temp_path)
        params = StdioServerParameters(
            command=MCP_COMMAND[0], args=MCP_COMMAND[1:], env=env
        )
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    for query_spec in queries:
                        record: dict[str, Any] = {"query": query_spec}
                        try:
                            payload = await session.call_tool(
                                "search",
                                {"action": "search", "query": query_spec["query"]},
                            )
                            data = _payload(payload)
                            raw_results = data.get("results", [])
                            if not isinstance(raw_results, list):
                                raise ValueError(
                                    "MCP search payload has non-list results"
                                )
                            score = score_one(query_spec, raw_results)
                            record.update({"score": score, "results": raw_results})
                        except (
                            Exception
                        ) as exc:  # Keep all query ids visible in a baseline run.
                            record.update(
                                {
                                    "score": score_one(query_spec, []),
                                    "results": [],
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )
                        records.append(record)
        except Exception as exc:
            runner_error = f"{type(exc).__name__}: {exc}"
            records = [
                {
                    "query": query_spec,
                    "score": score_one(query_spec, []),
                    "results": [],
                    "error": runner_error,
                }
                for query_spec in queries
            ]
    return _build_report(records, runner_error=runner_error, provenance=provenance)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay-artifact", type=Path)
    mode.add_argument("--replay-rerank-artifact", type=Path)
    mode.add_argument(
        "--compare-artifacts",
        type=Path,
        nargs=2,
        metavar=("BEFORE", "AFTER"),
    )
    args = parser.parse_args(raw_argv)
    queries = load_queries(args.query_file)
    if args.replay_rerank_artifact and args.limit is not None:
        parser.error("--limit cannot be used with --replay-rerank-artifact")
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        queries = queries[: args.limit]
    if args.compare_artifacts:
        execution_mode = "comparison"
    elif args.replay_rerank_artifact:
        execution_mode = "replay_rerank"
    elif args.replay_artifact:
        execution_mode = "replay"
    else:
        execution_mode = "live_protocol"
    command = [sys.executable, str(Path(__file__).resolve()), *raw_argv]
    provenance = build_provenance(
        query_path=args.query_file,
        command=command,
        execution_mode=execution_mode,
    )
    if args.compare_artifacts:
        before_path, after_path = args.compare_artifacts
        result = compare_artifacts(
            _load_artifact(before_path),
            _load_artifact(after_path),
            queries,
            provenance=provenance,
        )
    elif args.replay_rerank_artifact:
        result = asyncio.run(
            replay_rerank_artifact(
                _load_artifact(args.replay_rerank_artifact),
                queries,
                provenance=provenance,
            )
        )
    elif args.replay_artifact:
        result = replay_artifact(
            _load_artifact(args.replay_artifact),
            queries,
            provenance=provenance,
        )
    else:
        result = asyncio.run(run(queries, provenance=provenance))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
