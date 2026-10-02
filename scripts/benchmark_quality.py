"""Wet MCP Runtime Quality and Benchmark Runner.

Consumes wet-quality-corpus.jsonl and produces machine-readable JSONL results
and aggregate metrics for baseline and ablation comparisons.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Fix console encoding on Windows
if sys.platform == "win32":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(_s, io.TextIOWrapper):
            _s.reconfigure(encoding="utf-8", errors="replace")


class FailureClass:
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    SSRF_BLOCKED = "SSRF_BLOCKED"
    AUTH_FAILED = "AUTH_FAILED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    EMPTY_RESULTS = "EMPTY_RESULTS"
    EXTRACTION_PARSE_ERROR = "EXTRACTION_PARSE_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
    UNKNOWN = "UNKNOWN"


REQUIRED_CORPUS_FIELDS = {
    "id",
    "query",
    "source_url",
    "expected_type",
    "expected_fields",
    "freshness_class",
    "provenance",
}


@dataclass
class CorpusItem:
    id: str
    query: str
    source_url: str
    expected_type: str  # "search" | "extract" | "docs"
    expected_fields: list[str]
    freshness_class: str  # "static" | "rolling" | "spec"
    provenance: str
    expected_relevance: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    corpus_id: str
    mode: str
    backend: str
    model_chain: str
    coverage: float
    precision: float
    latency_ms: float
    cost_estimate: float
    failures: str
    round_trip_hash: str
    status: str  # "PASS" | "FAIL"
    cost_basis: str = "unavailable"
    raw_item_count: int = 0
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_corpus_item(data: dict[str, Any]) -> CorpusItem:
    missing = REQUIRED_CORPUS_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"missing required fields: {sorted(missing)}")
    if not isinstance(data["expected_fields"], list):
        raise ValueError("expected_fields must be a list of strings")
    relevance = data.get("expected_relevance", {})
    if not isinstance(relevance, dict):
        raise ValueError("expected_relevance must be an object")
    normalized_relevance: dict[str, list[str]] = {}
    for key, values in relevance.items():
        if not isinstance(values, list):
            raise ValueError(f"expected_relevance.{key} must be a list of strings")
        normalized_relevance[str(key)] = [str(value).lower() for value in values]
    return CorpusItem(
        id=str(data["id"]),
        query=str(data["query"]),
        source_url=str(data["source_url"]),
        expected_type=str(data["expected_type"]),
        expected_fields=[str(f) for f in data["expected_fields"]],
        freshness_class=str(data["freshness_class"]),
        provenance=str(data["provenance"]),
        expected_relevance=normalized_relevance,
    )


def load_corpus(path: Path) -> list[CorpusItem]:
    if not path.exists():
        raise FileNotFoundError(f"Corpus file not found: {path}")
    items: list[CorpusItem] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            item = validate_corpus_item(raw)
            items.append(item)
        except Exception as err:
            raise ValueError(f"Line {line_num} invalid in {path}: {err}") from err
    if not items:
        raise ValueError(f"no valid items found in {path}")
    return items


@contextmanager
def benchmark_environment(backend: str, model_chain: str) -> Iterator[None]:
    """Apply one benchmark configuration and restore the process environment."""
    overrides: dict[str, str | None] = {
        "SEARCH_BACKENDS": backend,
        "EMBEDDING_MODELS": None if model_chain == "none" else model_chain,
        "RERANK_MODELS": None if model_chain == "none" else model_chain,
        "LLM_MODELS": None if model_chain == "none" else model_chain,
    }
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def score_search_results(
    item: CorpusItem, results: Sequence[dict[str, Any]]
) -> tuple[float, float]:
    """Return field coverage and judged relevance precision for search results."""
    if not results:
        return 0.0, 0.0

    def has_expected_fields(result: dict[str, Any]) -> bool:
        return all(
            key in result or (key == "snippet" and bool(result.get("content")))
            for key in item.expected_fields
        )

    field_coverage = sum(has_expected_fields(result) for result in results) / len(
        results
    )
    relevance = item.expected_relevance
    domains = relevance.get("domains", [])
    terms = relevance.get("terms", [])
    if not domains and not terms:
        return field_coverage, field_coverage

    relevant = 0
    for result in results:
        url = str(result.get("url") or "").strip()
        host = urlsplit(url).netloc.lower()
        haystack = " ".join(
            str(result.get(key) or "") for key in ("title", "snippet", "content")
        ).lower()
        domain_hit = any(
            host == domain or host.endswith(f".{domain}") for domain in domains
        )
        term_hit = any(term in haystack for term in terms)
        relevant += int(domain_hit or term_hit)
    return field_coverage, relevant / len(results)


def normalize_extraction_hash(content: str) -> str:
    """Compute sha256 hash of normalized text."""
    normalized = re.sub(r"\s+", " ", content.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimate_cost(
    backend: str = "searxng",
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> float:
    """Rough request cost estimate in USD based on observed tokens/backend."""
    if backend == "searxng" and not model:
        return 0.0
    # Jina embedding: ~$0.02 / 1M tokens
    if "jina-embeddings" in model or "jina" in model:
        return (tokens_in / 1_000_000) * 0.02
    # OpenRouter/Minimax: ~$0.20 / 1M input, $1.10 / 1M output
    if "minimax" in model:
        return (tokens_in / 1_000_000) * 0.20 + (tokens_out / 1_000_000) * 1.10
    # Tavily API: ~$0.005 / request
    if backend == "tavily":
        return 0.005
    return 0.0


def compute_metrics(results: Sequence[BenchmarkResult]) -> dict[str, Any]:
    if not results:
        return {
            "total_cases": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "pass_rate": 0.0,
            "mean_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "mean_coverage": 0.0,
            "mean_precision": 0.0,
            "total_cost_estimate": 0.0,
            "failure_breakdown": {},
        }

    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = total - passed

    latencies = sorted(r.latency_ms for r in results)
    p50_idx = int(total * 0.5)
    p95_idx = min(total - 1, int(total * 0.95))

    mean_lat = sum(latencies) / total
    p50_lat = latencies[p50_idx]
    p95_lat = latencies[p95_idx]

    mean_cov = sum(r.coverage for r in results) / total
    mean_prec = sum(r.precision for r in results) / total
    total_cost = sum(r.cost_estimate for r in results)

    failure_counts: dict[str, int] = {}
    for r in results:
        if r.failures != FailureClass.NONE:
            failure_counts[r.failures] = failure_counts.get(r.failures, 0) + 1

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "pass_rate": passed / total,
        "mean_latency_ms": mean_lat,
        "p50_latency_ms": p50_lat,
        "p95_latency_ms": p95_lat,
        "mean_coverage": mean_cov,
        "mean_precision": mean_prec,
        "total_cost_estimate": total_cost,
        "failure_breakdown": failure_counts,
    }


async def run_single_case(
    item: CorpusItem,
    mode: str = "stdio",
    backend: str = "searxng",
    model_chain: str = "none",
) -> BenchmarkResult:
    """Run a single benchmark test case using direct wet_mcp server calls."""
    if mode != "stdio":
        return BenchmarkResult(
            corpus_id=item.id,
            mode=mode,
            backend=backend,
            model_chain=model_chain,
            coverage=0.0,
            precision=0.0,
            latency_ms=0.0,
            cost_estimate=0.0,
            failures=FailureClass.UNSUPPORTED_MODE,
            round_trip_hash="",
            status="FAIL",
            error_message=(
                "Direct benchmark execution supports stdio only; "
                "hosted/local-relay runs require the MCP protocol harness."
            ),
        )
    try:
        import wet_mcp.transport_check as tc

        tc._UVX_TOOL_VENV_CACHE = False
        from wet_mcp.credential_state import CredentialState, set_state

        set_state(CredentialState.LOCAL)
        from wet_mcp import server as wet_server

        if wet_server._docs_db is None:
            try:
                wet_server._docs_db = wet_server.make_docs_db()
            except Exception:
                pass
        from wet_mcp.server import extract, search
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        import wet_mcp.transport_check as tc

        tc._UVX_TOOL_VENV_CACHE = False
        from wet_mcp.credential_state import CredentialState, set_state

        set_state(CredentialState.LOCAL)
        from wet_mcp import server as wet_server

        if wet_server._docs_db is None:
            try:
                wet_server._docs_db = wet_server.make_docs_db()
            except Exception:
                pass
        from wet_mcp.server import extract, search
    t0 = time.perf_counter()
    status = "FAIL"
    failure_class = FailureClass.NONE
    error_msg = ""
    round_trip_hash = ""
    coverage = 0.0
    precision = 0.0
    raw_count = 0

    def _unwrap_result(res: Any) -> dict[str, Any]:
        if hasattr(res, "structuredContent") and res.structuredContent:
            return res.structuredContent
        if hasattr(res, "content") and res.content and hasattr(res.content[0], "text"):
            try:
                return json.loads(res.content[0].text)
            except Exception:
                return {"raw_text": res.content[0].text}
        if isinstance(res, dict):
            return res
        return {}

    try:
        if item.expected_type == "search":
            call_res = await search(action="search", query=item.query)
            t1 = time.perf_counter()
            lat_ms = (t1 - t0) * 1000.0
            res = _unwrap_result(call_res)

            if "error" in res and not res.get("results"):
                err_str = str(res["error"]).lower()
                if any(
                    marker in err_str
                    for marker in (
                        "needs a search backend",
                        "cannot auto-start",
                        "no search backend",
                        "searxng",
                    )
                ):
                    failure_class = FailureClass.BACKEND_UNAVAILABLE
                else:
                    failure_class = FailureClass.NETWORK_ERROR
                status = "FAIL"
                error_msg = str(res["error"])
            else:
                results_list = [
                    result
                    for result in res.get("results", [])
                    if isinstance(result, dict)
                ]
                raw_count = len(results_list)
                if raw_count == 0:
                    failure_class = FailureClass.EMPTY_RESULTS
                    status = "FAIL"
                else:
                    coverage, precision = score_search_results(item, results_list)
                    round_trip_hash = hashlib.sha256(
                        json.dumps(results_list[:3], sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    status = "PASS" if coverage > 0.0 and precision > 0.0 else "FAIL"

        elif item.expected_type == "extract":
            call_res = await extract(action="extract", urls=[item.source_url])
            t1 = time.perf_counter()
            lat_ms = (t1 - t0) * 1000.0
            res = _unwrap_result(call_res)
            results_list = res.get("results", [])
            first_item = (
                results_list[0]
                if results_list and isinstance(results_list[0], dict)
                else res
            )
            text_content = (
                first_item.get("markdown")
                or first_item.get("clean_text")
                or first_item.get("content")
                or ""
            )

            if first_item.get("error") and not text_content:
                failure_class = FailureClass.NETWORK_ERROR
                status = "FAIL"
                error_msg = str(first_item["error"])
            elif "error" in res and not text_content:
                failure_class = FailureClass.NETWORK_ERROR
                status = "FAIL"
                error_msg = str(res["error"])
            elif text_content:
                round_trip_hash = normalize_extraction_hash(text_content)
                has_fields = sum(
                    1
                    for key in item.expected_fields
                    if key in first_item or (key == "markdown" and text_content)
                )
                coverage = (
                    has_fields / len(item.expected_fields)
                    if item.expected_fields
                    else 1.0
                )
                precision = 1.0 if coverage >= 0.6 else coverage
                status = "PASS" if coverage >= 0.5 else "FAIL"
                raw_count = len(results_list) if results_list else 1
            else:
                failure_class = FailureClass.EMPTY_RESULTS
                status = "FAIL"
                error_msg = "empty extraction result"

        elif item.expected_type == "docs":
            lib_name = item.query.split()[0]
            call_res = await search(action="docs_resolve", query=lib_name)
            t1 = time.perf_counter()
            lat_ms = (t1 - t0) * 1000.0
            res = _unwrap_result(call_res)

            results_list = res.get("results") or res.get("libraries") or []
            raw_count = len(results_list)
            if raw_count > 0 or ("error" not in res and res):
                coverage = 1.0
                precision = 1.0
                round_trip_hash = hashlib.sha256(
                    json.dumps(res, sort_keys=True).encode("utf-8")
                ).hexdigest()
                status = "PASS"
            else:
                failure_class = FailureClass.EMPTY_RESULTS
                status = "FAIL"
                error_msg = str(
                    res.get("error") if isinstance(res, dict) else "no docs results"
                )
        else:
            lat_ms = (time.perf_counter() - t0) * 1000.0
            failure_class = FailureClass.UNKNOWN
            status = "FAIL"
            error_msg = f"Unknown expected_type: {item.expected_type}"
    except TimeoutError:
        lat_ms = (time.perf_counter() - t0) * 1000.0
        failure_class = FailureClass.TIMEOUT
        status = "FAIL"
        error_msg = "Operation timed out"
    except Exception as err:
        lat_ms = (time.perf_counter() - t0) * 1000.0
        err_str = str(err).lower()
        if "ssrf" in err_str or "forbidden" in err_str:
            failure_class = FailureClass.SSRF_BLOCKED
        elif "auth" in err_str or "unauthorized" in err_str:
            failure_class = FailureClass.AUTH_FAILED
        elif "rate" in err_str or "429" in err_str:
            failure_class = FailureClass.RATE_LIMITED
        else:
            failure_class = FailureClass.NETWORK_ERROR
        status = "FAIL"
        error_msg = str(err)

    if status != "PASS":
        cost = 0.0
        cost_basis = "not_attempted"
    elif backend == "searxng" and model_chain == "none":
        cost = 0.0
        cost_basis = "no_provider_cost"
    elif backend == "tavily":
        cost = estimate_cost(backend=backend, model=model_chain)
        cost_basis = "known_request_rate"
    else:
        cost = 0.0
        cost_basis = "usage_unavailable"

    return BenchmarkResult(
        corpus_id=item.id,
        mode=mode,
        backend=backend,
        model_chain=model_chain,
        coverage=coverage,
        precision=precision,
        latency_ms=lat_ms,
        cost_estimate=cost,
        cost_basis=cost_basis,
        failures=failure_class,
        round_trip_hash=round_trip_hash,
        status=status,
        raw_item_count=raw_count,
        error_message=error_msg,
    )


async def run_benchmark(
    corpus: list[CorpusItem],
    mode: str = "stdio",
    backend: str = "searxng",
    model_chain: str = "none",
    ids: set[str] | None = None,
) -> tuple[list[BenchmarkResult], dict[str, Any]]:
    filtered = [c for c in corpus if not ids or c.id in ids]
    results: list[BenchmarkResult] = []
    with benchmark_environment(backend, model_chain):
        for item in filtered:
            res = await run_single_case(
                item,
                mode=mode,
                backend=backend,
                model_chain=model_chain,
            )
            results.append(res)
    metrics = compute_metrics(results)
    return results, metrics


def write_results_jsonl(
    path: Path,
    results: Sequence[BenchmarkResult],
    metrics: dict[str, Any],
    *,
    mode: str,
    backend: str,
    model_chain: str,
) -> None:
    """Write per-case records followed by one aggregate record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for result in results:
            output.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        output.write(
            json.dumps(
                {
                    "record_type": "aggregate",
                    "mode": mode,
                    "backend": backend,
                    "model_chain": model_chain,
                    "metrics": metrics,
                },
                sort_keys=True,
            )
            + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Wet MCP Quality Benchmark Runner")
    parser.add_argument(
        "--corpus",
        type=str,
        default="tests/fixtures/benchmark/wet-quality-corpus.jsonl",
        help="Path to corpus JSONL",
    )
    parser.add_argument(
        "--output-jsonl",
        type=str,
        default=None,
        help="Path to save output results JSONL",
    )
    parser.add_argument(
        "--output-summary", type=str, default=None, help="Path to save summary JSON"
    )
    parser.add_argument(
        "--mode", type=str, default="stdio", choices=["stdio", "hosted", "local-relay"]
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="searxng",
        choices=["searxng", "tavily", "brave", "exa"],
    )
    parser.add_argument(
        "--model-chain", type=str, default="none", help="Model chain identifier"
    )
    parser.add_argument(
        "--ids", type=str, default=None, help="Comma-separated IDs to run"
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    corpus = load_corpus(corpus_path)
    id_set = set(args.ids.split(",")) if args.ids else None
    selected_count = sum(1 for item in corpus if not id_set or item.id in id_set)

    print(
        f"Running benchmark on {selected_count} cases (mode={args.mode}, backend={args.backend})..."
    )
    results, metrics = asyncio.run(
        run_benchmark(
            corpus,
            mode=args.mode,
            backend=args.backend,
            model_chain=args.model_chain,
            ids=id_set,
        )
    )

    if args.output_jsonl:
        out_path = Path(args.output_jsonl)
        write_results_jsonl(
            out_path,
            results,
            metrics,
            mode=args.mode,
            backend=args.backend,
            model_chain=args.model_chain,
        )
        print(f"Results written to {out_path}")

    if args.output_summary:
        summary_path = Path(args.output_summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Summary written to {summary_path}")

    print(
        f"Benchmark finished: {metrics['passed_cases']}/{metrics['total_cases']} passed (rate: {metrics['pass_rate']:.1%}), mean latency: {metrics['mean_latency_ms']:.1f}ms"
    )
    return 0 if metrics["failed_cases"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
