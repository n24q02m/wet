"""Tests for the wet benchmark quality runner and metrics."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.benchmark_quality import (
    BenchmarkResult,
    CorpusItem,
    FailureClass,
    benchmark_environment,
    compute_metrics,
    estimate_cost,
    load_corpus,
    normalize_extraction_hash,
    run_single_case,
    score_search_results,
    write_results_jsonl,
)


def test_load_corpus_valid(tmp_path: Path):
    corpus_file = tmp_path / "test-corpus.jsonl"
    item1 = {
        "id": "c1",
        "query": "test query 1",
        "source_url": "https://example.com/doc1",
        "expected_type": "search",
        "expected_fields": ["title", "url"],
        "freshness_class": "static",
        "provenance": "test-prov",
    }
    item2 = {
        "id": "c2",
        "query": "test query 2",
        "source_url": "https://example.com/doc2",
        "expected_type": "extract",
        "expected_fields": ["markdown", "title"],
        "freshness_class": "spec",
        "provenance": "test-prov",
    }
    corpus_file.write_text(
        f"{json.dumps(item1)}\n{json.dumps(item2)}\n", encoding="utf-8"
    )

    loaded = load_corpus(corpus_file)
    assert len(loaded) == 2
    assert loaded[0].id == "c1"
    assert loaded[0].expected_type == "search"
    assert loaded[1].id == "c2"
    assert loaded[1].expected_type == "extract"


def test_load_corpus_invalid_schema(tmp_path: Path):
    corpus_file = tmp_path / "invalid-corpus.jsonl"
    invalid_item = {"id": "bad1"}  # Missing required fields
    corpus_file.write_text(json.dumps(invalid_item) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields"):
        load_corpus(corpus_file)


def test_load_corpus_empty_file(tmp_path: Path):
    corpus_file = tmp_path / "empty-corpus.jsonl"
    corpus_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no valid items found"):
        load_corpus(corpus_file)


def test_normalize_extraction_hash():
    text1 = "  # Heading \n\n Some   content with   spaces.  \n"
    text2 = "# Heading\nSome content with spaces."

    hash1 = normalize_extraction_hash(text1)
    hash2 = normalize_extraction_hash(text2)

    assert hash1 == hash2
    assert len(hash1) == 64  # sha256 hex string


def test_score_search_results_uses_judged_relevance():
    item = CorpusItem(
        id="search-1",
        query="containers",
        source_url="https://developers.cloudflare.com/containers/",
        expected_type="search",
        expected_fields=["title", "url", "snippet"],
        freshness_class="static",
        provenance="test",
        expected_relevance={
            "domains": ["developers.cloudflare.com"],
            "terms": ["containers"],
        },
    )
    results = [
        {
            "title": "Containers",
            "url": "https://developers.cloudflare.com/containers/",
            "snippet": "Run containers with Workers.",
        },
        {
            "title": "Unrelated",
            "url": "https://example.com/",
            "snippet": "A different topic.",
        },
    ]

    coverage, precision = score_search_results(item, results)
    assert coverage == pytest.approx(1.0)
    assert precision == pytest.approx(0.5)


def test_compute_metrics_aggregation():
    results = [
        BenchmarkResult(
            corpus_id="c1",
            mode="stdio",
            backend="searxng",
            model_chain="none",
            coverage=1.0,
            precision=1.0,
            latency_ms=120.0,
            cost_estimate=0.0001,
            failures=FailureClass.NONE,
            round_trip_hash="hash1",
            status="PASS",
        ),
        BenchmarkResult(
            corpus_id="c2",
            mode="stdio",
            backend="searxng",
            model_chain="none",
            coverage=0.8,
            precision=0.75,
            latency_ms=250.0,
            cost_estimate=0.0002,
            failures=FailureClass.NONE,
            round_trip_hash="hash2",
            status="PASS",
        ),
        BenchmarkResult(
            corpus_id="c3",
            mode="stdio",
            backend="searxng",
            model_chain="none",
            coverage=0.0,
            precision=0.0,
            latency_ms=500.0,
            cost_estimate=0.0,
            failures=FailureClass.EMPTY_RESULTS,
            round_trip_hash="",
            status="FAIL",
        ),
    ]

    metrics = compute_metrics(results)
    assert metrics["total_cases"] == 3
    assert metrics["passed_cases"] == 2
    assert metrics["failed_cases"] == 1
    assert metrics["pass_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert metrics["mean_latency_ms"] == pytest.approx((120 + 250 + 500) / 3, rel=1e-3)
    assert metrics["p50_latency_ms"] == pytest.approx(250.0, rel=1e-3)
    assert metrics["mean_coverage"] == pytest.approx((1.0 + 0.8 + 0.0) / 3, rel=1e-3)
    assert metrics["mean_precision"] == pytest.approx((1.0 + 0.75 + 0.0) / 3, rel=1e-3)
    assert metrics["failure_breakdown"][FailureClass.EMPTY_RESULTS] == 1


def test_estimate_cost():
    cost_free = estimate_cost(backend="searxng", tokens_in=0, tokens_out=0)
    assert cost_free == 0.0

    cost_llm = estimate_cost(
        backend="searxng",
        model="jina_ai/jina-embeddings-v5-text-small",
        tokens_in=1000,
        tokens_out=0,
    )
    assert cost_llm >= 0.0


def test_validate_corpus_fixture():
    fixture_path = (
        Path(__file__).parent / "fixtures" / "benchmark" / "wet-quality-corpus.jsonl"
    )
    assert fixture_path.exists(), "Benchmark corpus fixture must exist"
    corpus = load_corpus(fixture_path)
    assert len(corpus) >= 15, "Benchmark corpus must have sufficient test cases"
    types = {item.expected_type for item in corpus}
    assert "search" in types
    assert "extract" in types
    assert "docs" in types
    assert all(
        item.expected_relevance for item in corpus if item.expected_type == "search"
    )


def test_write_results_jsonl_includes_aggregate(tmp_path: Path):
    result = BenchmarkResult(
        corpus_id="c1",
        mode="stdio",
        backend="searxng",
        model_chain="none",
        coverage=1.0,
        precision=1.0,
        latency_ms=10.0,
        cost_estimate=0.0,
        failures=FailureClass.NONE,
        round_trip_hash="hash",
        status="PASS",
    )
    output = tmp_path / "results.jsonl"
    write_results_jsonl(
        output,
        [result],
        {"total_cases": 1, "passed_cases": 1},
        mode="stdio",
        backend="searxng",
        model_chain="none",
    )

    rows = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["corpus_id"] == "c1"
    assert rows[-1]["record_type"] == "aggregate"
    assert rows[-1]["metrics"]["passed_cases"] == 1


@pytest.mark.asyncio
async def test_non_stdio_mode_fails_closed():
    item = CorpusItem(
        id="hosted-1",
        query="test",
        source_url="https://example.com",
        expected_type="search",
        expected_fields=["title"],
        freshness_class="static",
        provenance="test",
    )

    result = await run_single_case(item, mode="hosted")
    assert result.status == "FAIL"
    assert result.failures == FailureClass.UNSUPPORTED_MODE
    assert "protocol harness" in result.error_message


def test_benchmark_environment_scoped(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng")
    monkeypatch.setenv("LLM_MODELS", "old/model")

    with benchmark_environment("tavily", "none"):
        assert os.environ["SEARCH_BACKENDS"] == "tavily"
        assert "LLM_MODELS" not in os.environ

    assert os.environ["SEARCH_BACKENDS"] == "searxng"
    assert os.environ["LLM_MODELS"] == "old/model"
