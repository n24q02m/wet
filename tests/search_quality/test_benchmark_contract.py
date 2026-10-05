from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import benchmark_contract as contract
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_derivation_audits_conflicting_source_ids_and_keeps_exact_targets():
    derived = contract.derive_fixture_records(REPO_ROOT)

    assert derived.source_audit == {
        "source_records": 2000,
        "unique_source_ids": 1958,
        "conflicting_duplicate_ids": 42,
        "unambiguous_source_records": 1916,
    }
    assert len(derived.extract_urls) == 200
    assert len(derived.web_search_queries) == 500
    assert len(derived.docs_recall_cases) == 200
    assert len(derived.docs_corpus) == 1916

    benchmark_ids = [
        row["id"]
        for rows in (
            derived.extract_urls,
            derived.web_search_queries,
            derived.docs_recall_cases,
            derived.docs_corpus,
        )
        for row in rows
    ]
    assert len(benchmark_ids) == len(set(benchmark_ids))


def test_committed_v1_fixtures_are_immutable_derivation_and_validate():
    expected = contract.render_fixture_files(
        contract.derive_fixture_records(REPO_ROOT), REPO_ROOT
    )
    fixture_root = contract.DEFAULT_FIXTURE_ROOT

    assert {path.name for path in fixture_root.iterdir()} == set(expected)
    for name, content in expected.items():
        assert (fixture_root / name).read_bytes() == content

    proof = contract.validate_fixture_set(fixture_root)
    assert proof["counts"] == {
        "extract_urls": 200,
        "web_search_queries": 500,
        "docs_recall_cases": 200,
        "docs_corpus": 1916,
    }
    assert all(len(digest) == 64 for digest in proof["sha256"].values())


def test_web_quality_requires_library_and_multi_term_intent_and_rewards_order():
    case = {
        "id": "web-v1-regression",
        "library_terms": ["sqlite"],
        "intent_terms": ["write ahead log", "concurrent readers"],
        "min_intent_terms": 2,
    }
    generic = [
        {
            "url": "https://example.test/sqlite",
            "title": "SQLite overview",
            "snippet": "SQLite is an embedded relational database.",
        }
    ]
    assert contract.score_web_case(case, generic)["hits_at_10"] == 0

    relevant = {
        "url": "https://example.test/sqlite-wal",
        "title": "SQLite write ahead log",
        "snippet": "Configure WAL for concurrent readers.",
    }
    distractors = [
        {
            "url": f"https://example.test/noise-{index}",
            "title": "Database article",
            "snippet": "Generic database notes.",
        }
        for index in range(9)
    ]
    late = contract.score_web_case(case, [*distractors, relevant])
    early = contract.score_web_case(case, [relevant, *distractors])

    assert late["hits_at_10"] == early["hits_at_10"] == 1
    assert early["ndcg_at_10"] > late["ndcg_at_10"]


def test_percentiles_use_deterministic_nearest_rank():
    assert contract.percentile_nearest_rank([40, 10, 30, 20], 0.50) == 20
    assert contract.percentile_nearest_rank([40, 10, 30, 20], 0.95) == 40
    with pytest.raises(ValueError, match="non-empty"):
        contract.percentile_nearest_rank([], 0.50)


@pytest.mark.asyncio
async def test_case_runners_call_public_mcp_tools_through_session():
    class RecordingSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def call_tool(self, name: str, arguments: dict):
            self.calls.append((name, arguments))
            if name == "extract":
                data = {
                    "results": [
                        {
                            "url": arguments["urls"][0],
                            "clean_text": "Useful content " * 20,
                            "markdown": "Useful content " * 20,
                        }
                    ]
                }
            elif arguments["action"] == "docs_query":
                data = {
                    "results": [
                        {
                            "url": "https://benchmark.invalid/docs/chunk-v1-1",
                            "title": "Async session transaction",
                            "content": "Async session transaction patterns",
                        }
                    ]
                }
            else:
                data = {
                    "results": [
                        {
                            "url": "https://example.test/sqlalchemy-async",
                            "title": "SQLAlchemy async session",
                            "snippet": "Manage an async session transaction.",
                        }
                    ]
                }
            return SimpleNamespace(structuredContent=data, content=[])

    session = RecordingSession()
    extract_record = await contract.run_extract_case(
        session,
        {
            "id": "extract-v1-1",
            "url": "https://example.test",
            "min_content_chars": 50,
            "min_clean_ratio": 0.70,
        },
    )
    web_record = await contract.run_web_case(
        session,
        {
            "id": "web-v1-1",
            "query": "sqlalchemy async session transaction",
            "library_terms": ["sqlalchemy"],
            "intent_terms": ["async session", "transaction"],
            "min_intent_terms": 2,
        },
    )
    docs_record = await contract.run_docs_case(
        session,
        {
            "id": "docs-v1-1",
            "library": "sqlalchemy",
            "query": "async session transaction",
            "expected_chunk_ids": ["chunk-v1-1"],
        },
    )

    assert [name for name, _ in session.calls] == ["extract", "search", "search"]
    assert session.calls[0][1]["action"] == "extract"
    assert session.calls[1][1]["action"] == "search"
    assert session.calls[2][1]["action"] == "docs_query"
    assert extract_record["success"] is True
    assert web_record["hits_at_10"] == 1
    assert docs_record["recall_at_10"] == 1.0


def _passing_artifact(
    fixture_proof: dict, commit_sha: str, *, backend: str = "searxng"
) -> dict:
    return {
        "schema_version": contract.ARTIFACT_SCHEMA_VERSION,
        "contract_version": contract.CONTRACT_VERSION,
        "complete": True,
        "provenance": {
            "git": {"commit": commit_sha, "dirty": False},
            "fixtures": fixture_proof,
            "protocol": {
                "client": "mcp.ClientSession",
                "transport": contract.PROTOCOL_TRANSPORT,
            },
            "command": ["uv", "run", "python", "tests/search_quality/run_contract.py"],
            "environment": {"config_sha256": "a" * 64},
            "thresholds_effective": {
                "web_search_p95_ms": contract.web_search_p95_threshold(backend),
                "web_search_backend": backend,
            },
        },
        "suites": {
            "extract": {
                "case_count": 200,
                "metrics": {
                    "p50_latency_ms": 100.0,
                    "p95_latency_ms": 500.0,
                    "success_rate": 0.99,
                    "clean_pass_rate": 0.90,
                    "mean_clean_ratio": 0.85,
                },
                "records": [{"id": f"extract-{index}"} for index in range(200)],
            },
            "web_search": {
                "backend": backend,
                "case_count": 500,
                "metrics": {
                    "p50_latency_ms": 400.0,
                    "p95_latency_ms": 1500.0,
                    "success_rate": 0.99,
                    "mean_hits_at_10": 1.5,
                    "mean_ndcg_at_10": 0.80,
                },
                "records": [{"id": f"web-{index}"} for index in range(500)],
            },
            "docs_recall": {
                "case_count": 200,
                "metrics": {
                    "p50_latency_ms": 100.0,
                    "p95_latency_ms": 400.0,
                    "success_rate": 1.0,
                    "recall_at_10": 0.90,
                },
                "records": [{"id": f"docs-{index}"} for index in range(200)],
            },
        },
    }


def test_release_gate_is_fail_closed_for_null_incomplete_or_wrong_sha():
    fixture_proof = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)
    artifact = _passing_artifact(fixture_proof, "b" * 40)
    contract.validate_release_artifact(
        artifact,
        expected_commit="b" * 40,
        fixture_root=contract.DEFAULT_FIXTURE_ROOT,
    )

    missing_metric = json.loads(json.dumps(artifact))
    missing_metric["suites"]["docs_recall"]["metrics"]["recall_at_10"] = None
    with pytest.raises(contract.ContractError, match="null"):
        contract.validate_release_artifact(
            missing_metric,
            expected_commit="b" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )

    incomplete = json.loads(json.dumps(artifact))
    incomplete["complete"] = False
    with pytest.raises(contract.ContractError, match="complete"):
        contract.validate_release_artifact(
            incomplete,
            expected_commit="b" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )

    with pytest.raises(contract.ContractError, match="commit"):
        contract.validate_release_artifact(
            artifact,
            expected_commit="c" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )


def test_release_gate_enforces_p95_for_direct_search_backends():
    fixture_proof = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)

    passing = _passing_artifact(fixture_proof, "b" * 40, backend="searxng")
    warnings = contract.validate_release_artifact(
        passing,
        expected_commit="b" * 40,
        fixture_root=contract.DEFAULT_FIXTURE_ROOT,
    )
    assert warnings == []

    slow = json.loads(json.dumps(passing))
    slow["suites"]["web_search"]["metrics"]["p95_latency_ms"] = 5000.0
    with pytest.raises(contract.ContractError, match="p95_latency_ms"):
        contract.validate_release_artifact(
            slow,
            expected_commit="b" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )


def test_release_gate_reports_but_skips_p95_for_llm_mediated_backends():
    fixture_proof = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)

    slow_llm = _passing_artifact(fixture_proof, "b" * 40, backend="openrouter")
    slow_llm["suites"]["web_search"]["metrics"]["p95_latency_ms"] = 45000.0
    warnings = contract.validate_release_artifact(
        slow_llm,
        expected_commit="b" * 40,
        fixture_root=contract.DEFAULT_FIXTURE_ROOT,
    )
    assert len(warnings) == 1
    assert "45000.0" in warnings[0]
    assert "openrouter" in warnings[0]

    # A direct backend artifact must not smuggle a skipped ceiling.
    mismatched = _passing_artifact(fixture_proof, "b" * 40, backend="searxng")
    mismatched["provenance"]["thresholds_effective"]["web_search_p95_ms"] = None
    with pytest.raises(contract.ContractError, match="inconsistent"):
        contract.validate_release_artifact(
            mismatched,
            expected_commit="b" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )

    # Declared backend and recorded backend must agree.
    lying = _passing_artifact(fixture_proof, "b" * 40, backend="openrouter")
    lying["provenance"]["thresholds_effective"]["web_search_backend"] = "searxng"
    with pytest.raises(contract.ContractError, match="does not match"):
        contract.validate_release_artifact(
            lying,
            expected_commit="b" * 40,
            fixture_root=contract.DEFAULT_FIXTURE_ROOT,
        )


def test_provenance_distinguishes_revision_config_provider_and_command_without_secrets(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-never-record")
    monkeypatch.setenv("RERANK_PROVIDER", "openai")
    monkeypatch.setenv("SEARCH_BACKENDS", "searxng,brave")
    proof = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)

    provenance = contract.build_provenance(
        REPO_ROOT,
        fixture_proof=proof,
        command=["uv", "run", "benchmark"],
    )
    encoded = json.dumps(provenance, sort_keys=True)

    assert provenance["git"]["commit"]
    assert provenance["environment"]["safe_config"]["rerank_provider"] == "openai"
    assert provenance["environment"]["safe_config"]["search_backends"] == [
        "searxng",
        "brave",
    ]
    assert provenance["command"] == ["uv", "run", "benchmark"]
    assert "super-secret-never-record" not in encoded
    assert "OPENAI_API_KEY" not in encoded


def test_ci_and_release_workflows_wire_contract_and_exact_sha_gate():
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    cd = (REPO_ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    benchmark = (REPO_ROOT / ".github/workflows/benchmark.yml").read_text(
        encoding="utf-8"
    )

    assert "run_contract.py validate-fixtures" in ci
    assert "wet-benchmark-contract-${{ github.sha }}" in benchmark
    assert "run_contract.py run" in benchmark
    assert "benchmark_run_id" in cd
    assert "run_contract.py gate" in cd
    assert '--expected-commit "${GITHUB_SHA}"' in cd
    assert "needs: benchmark-contract" in cd
