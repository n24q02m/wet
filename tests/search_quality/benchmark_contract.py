"""Versioned 200/500/200 quality benchmark contract for wet-mcp.

The committed fixtures are mechanically derived from versioned repository
sources.  Live measurements always cross the MCP protocol boundary; this
module contains deterministic derivation, scoring, provenance, and gate logic.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

CONTRACT_VERSION = "wet-benchmark-contract-v1"
FIXTURE_SCHEMA_VERSION = "wet-benchmark-fixture-v1"
ARTIFACT_SCHEMA_VERSION = "wet-benchmark-artifact-v1"
DEFAULT_FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "v1"

TARGET_COUNTS = {
    "extract_urls": 200,
    "web_search_queries": 500,
    "docs_recall_cases": 200,
    "docs_corpus": 1916,
}
FIXTURE_FILES = {
    "extract_urls": "extract_urls.jsonl",
    "web_search_queries": "web_search_queries.jsonl",
    "docs_recall_cases": "docs_recall_cases.jsonl",
    "docs_corpus": "docs_corpus.jsonl",
}
REQUIRED_FILES = {
    *FIXTURE_FILES.values(),
    "manifest.jsonl",
    "PROVENANCE.txt",
}
SOURCE_LISTS = (
    ("tests/benchmark_docs_search.py", "BENCHMARK_CASES"),
    ("tests/benchmark_cases_cc_dp.py", "NEW_BENCHMARK_CASES"),
    ("tests/benchmark_cases_dq_ez.py", "NEW_BENCHMARK_CASES_DQ_EZ"),
    ("tests/benchmark_cases_fa_gj.py", "NEW_BENCHMARK_CASES_FA_GJ"),
)
SOURCE_PATHS = tuple(path for path, _ in SOURCE_LISTS) + (
    "src/wet/data/tier1_libraries.json",
    "tests/fixtures/urls/tier1_popular.txt",
)

THRESHOLDS = {
    "extract": {
        "success_rate": 0.95,
        "clean_pass_rate": 0.70,
        "mean_clean_ratio": 0.70,
    },
    "web_search": {
        "p95_latency_ms_max": 2000.0,
        "success_rate": 0.95,
        "mean_hits_at_10": 1.0,
        "mean_ndcg_at_10": 0.70,
    },
    "docs_recall": {
        "p95_latency_ms_max": 500.0,
        "success_rate": 0.95,
        "recall_at_10": 0.85,
    },
}

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_+#.-]*", re.IGNORECASE)
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "api",
        "as",
        "at",
        "by",
        "config",
        "configuration",
        "for",
        "from",
        "how",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "use",
        "using",
        "with",
    }
)
_SECRET_NAME_RE = re.compile(
    r"(?:api[_-]?key|token|secret|password|credential|private[_-]?key)", re.I
)


class ContractError(ValueError):
    """Raised when fixture or artifact data violates the benchmark contract."""


class ToolSession(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class DerivedFixtures:
    extract_urls: list[dict[str, Any]]
    web_search_queries: list[dict[str, Any]]
    docs_recall_cases: list[dict[str, Any]]
    docs_corpus: list[dict[str, Any]]
    source_audit: dict[str, int]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, source_id: str) -> str:
    return f"{prefix}-{_stable_key(source_id)[:16]}"


def _literal_list(path: Path, variable_name: str) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == variable_name
            for target in targets
        ):
            continue
        if node.value is None:
            continue
        raw = ast.literal_eval(node.value)
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            raise ContractError(f"{path}: {variable_name} must be a literal list")
        return raw
    raise ContractError(f"{path}: missing literal list {variable_name}")


def _load_docs_source(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records = [
        dict(record)
        for relative_path, variable_name in SOURCE_LISTS
        for record in _literal_list(repo_root / relative_path, variable_name)
    ]
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(records):
        for key in ("id", "library", "query", "tests_aspect"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ContractError(f"source record {index} needs non-empty {key}")
        by_id[record["id"]].append(record)

    conflicting = {
        source_id
        for source_id, group in by_id.items()
        if len(group) > 1 and len({_canonical_json(item) for item in group}) > 1
    }
    duplicate_ids = {source_id for source_id, group in by_id.items() if len(group) > 1}
    if duplicate_ids != conflicting:
        raise ContractError(
            "source duplicate audit changed: expected every duplicate to conflict"
        )

    unambiguous = [record for record in records if record["id"] not in duplicate_ids]
    audit = {
        "source_records": len(records),
        "unique_source_ids": len(by_id),
        "conflicting_duplicate_ids": len(conflicting),
        "unambiguous_source_records": len(unambiguous),
    }
    expected = {
        "source_records": 2000,
        "unique_source_ids": 1958,
        "conflicting_duplicate_ids": 42,
        "unambiguous_source_records": 1916,
    }
    if audit != expected:
        raise ContractError(
            f"docs source audit drifted: expected {expected}, got {audit}"
        )
    return unambiguous, audit


def _tokens(value: str) -> list[str]:
    return [token.lower().strip("._-") for token in _WORD_RE.findall(value)]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _library_terms(library: str) -> list[str]:
    normalized = " ".join(_tokens(library))
    parts = _tokens(re.sub(r"[-_./]", " ", library))
    terms = _unique([normalized, *parts])
    return [term for term in terms if len(term) >= 2]


def _intent_terms(query: str, library_terms: list[str]) -> list[str]:
    library_words = {word for term in library_terms for word in _tokens(term)}
    return _unique(
        [
            token
            for token in _tokens(query)
            if len(token) >= 3
            and token not in _STOPWORDS
            and token not in library_words
            and not token.isdigit()
        ]
    )


def _derive_web_cases(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible: list[tuple[dict[str, Any], list[str], list[str]]] = []
    for record in source:
        library_terms = _library_terms(record["library"])
        intent_terms = _intent_terms(record["query"], library_terms)
        if library_terms and len(intent_terms) >= 2:
            eligible.append((record, library_terms, intent_terms))
    eligible.sort(key=lambda item: (_stable_key(item[0]["id"]), item[0]["id"]))
    if len(eligible) < TARGET_COUNTS["web_search_queries"]:
        raise ContractError("docs source has fewer than 500 multi-intent web cases")

    return [
        {
            "schema_version": FIXTURE_SCHEMA_VERSION,
            "id": _stable_id("web-v1", record["id"]),
            "query": f"{record['library']} {record['query']}",
            "library_terms": library_terms,
            "intent_terms": intent_terms,
            "min_intent_terms": 2,
            "top_k": 10,
            "provenance": {
                "derivation": "library plus labeled query intent",
                "source_case_id": record["id"],
                "source_family": "docs-search-2000",
            },
        }
        for record, library_terms, intent_terms in eligible[
            : TARGET_COUNTS["web_search_queries"]
        ]
    ]


def _derive_docs_corpus(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in sorted(source, key=lambda item: item["id"]):
        chunk_id = _stable_id("chunk-v1", record["id"])
        language = record.get("language") or record.get("expect_lang") or "unspecified"
        rows.append(
            {
                "schema_version": FIXTURE_SCHEMA_VERSION,
                "id": _stable_id("corpus-v1", record["id"]),
                "chunk_id": chunk_id,
                "library": record["library"],
                "version": "benchmark-v1",
                "url": f"https://benchmark.invalid/docs/{chunk_id}",
                "title": record["query"],
                "content": (
                    f"Library: {record['library']}\n"
                    f"Question intent: {record['query']}\n"
                    f"Quality aspect: {record['tests_aspect']}\n"
                    f"Language: {language}"
                ),
                "topic": record["query"],
                "provenance": {
                    "derivation": "verbatim labeled fields from docs-search source",
                    "source_case_id": record["id"],
                    "source_family": "docs-search-2000",
                },
            }
        )
    return rows


def _derive_docs_cases(
    source: list[dict[str, Any]], corpus: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    library_counts = Counter(record["library"] for record in source)
    corpus_by_source_id = {
        record["provenance"]["source_case_id"]: record for record in corpus
    }
    eligible = [record for record in source if library_counts[record["library"]] >= 2]
    eligible.sort(key=lambda item: (_stable_key(item["id"]), item["id"]))
    if len(eligible) < TARGET_COUNTS["docs_recall_cases"]:
        raise ContractError("docs source has fewer than 200 non-trivial recall cases")
    rows = []
    for record in eligible[: TARGET_COUNTS["docs_recall_cases"]]:
        corpus_record = corpus_by_source_id[record["id"]]
        rows.append(
            {
                "schema_version": FIXTURE_SCHEMA_VERSION,
                "id": _stable_id("docs-v1", record["id"]),
                "library": record["library"],
                "query": record["query"],
                "expected_chunk_ids": [corpus_record["chunk_id"]],
                "top_k": 10,
                "provenance": {
                    "derivation": "hash-ranked case from a multi-case library",
                    "source_case_id": record["id"],
                    "source_family": "docs-search-2000",
                },
            }
        )
    return rows


def _canonical_registry_url(record: dict[str, Any]) -> tuple[str, str] | None:
    aspect = record["tests_aspect"].lower()
    library = record["library"].strip()
    mappings = (
        ("pypi", "pypi", f"https://pypi.org/project/{quote(library, safe='')}/"),
        ("npm", "npm", f"https://www.npmjs.com/package/{quote(library, safe='@/')}"),
        (
            "crates.io",
            "crates.io",
            f"https://crates.io/crates/{quote(library, safe='-_')}",
        ),
        (
            "rubygems",
            "rubygems",
            f"https://rubygems.org/gems/{quote(library, safe='-_')}",
        ),
        ("hex.pm", "hex", f"https://hex.pm/packages/{quote(library, safe='-_')}"),
        ("pub.dev", "pub", f"https://pub.dev/packages/{quote(library, safe='-_')}"),
        (
            "packagist",
            "packagist",
            f"https://packagist.org/packages/{quote(library, safe='/')}",
        ),
        (
            "nuget",
            "nuget",
            f"https://www.nuget.org/packages/{quote(library, safe='.-_')}",
        ),
    )
    for marker, registry, url in mappings:
        if marker in aspect:
            return registry, url
    return None


def _derive_extract_cases(
    repo_root: Path, source: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, str]] = {}

    def add(url: str, source_family: str, source_ref: str) -> None:
        normalized = url.strip().rstrip("/")
        parts = urlsplit(normalized)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return
        candidates.setdefault(
            normalized,
            {
                "url": normalized,
                "source_family": source_family,
                "source_ref": source_ref,
            },
        )

    starter_path = repo_root / "tests/fixtures/urls/tier1_popular.txt"
    for line_number, line in enumerate(
        starter_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        value = line.strip()
        if value and not value.startswith("#"):
            add(value, "tier1-url-starter", f"line:{line_number}")

    tier1_path = repo_root / "src/wet/data/tier1_libraries.json"
    tier1_data = json.loads(tier1_path.read_text(encoding="utf-8"))
    libraries = tier1_data.get("libraries", tier1_data)
    if not isinstance(libraries, list):
        raise ContractError("tier1_libraries.json must contain a libraries list")
    for item in libraries:
        if not isinstance(item, dict):
            raise ContractError("tier1 library entry must be an object")
        source_ref = str(item.get("name") or item.get("canonical_name") or "unknown")
        for key in ("homepage", "github_url", "docs_url"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                add(value, "tier1-library-metadata", f"{source_ref}:{key}")

    registry_candidates = []
    for record in source:
        mapped = _canonical_registry_url(record)
        if mapped:
            registry, url = mapped
            registry_candidates.append((record["id"], registry, url))
    registry_candidates.sort(key=lambda item: (_stable_key(item[0]), item[0]))
    for source_id, registry, url in registry_candidates:
        add(url, "docs-source-registry-url", f"{source_id}:{registry}")

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            {
                "tier1-url-starter": 0,
                "tier1-library-metadata": 1,
                "docs-source-registry-url": 2,
            }[item["source_family"]],
            _stable_key(item["url"]),
            item["url"],
        ),
    )
    if len(ordered) < TARGET_COUNTS["extract_urls"]:
        raise ContractError(f"only {len(ordered)} authoritative extract URLs available")
    return [
        {
            "schema_version": FIXTURE_SCHEMA_VERSION,
            "id": _stable_id("extract-v1", item["url"]),
            "url": item["url"],
            "min_content_chars": 80,
            "min_clean_ratio": 0.70,
            "provenance": {
                "derivation": "versioned repository URL or canonical registry URL",
                "source_family": item["source_family"],
                "source_ref": item["source_ref"],
            },
        }
        for item in ordered[: TARGET_COUNTS["extract_urls"]]
    ]


def derive_fixture_records(repo_root: Path) -> DerivedFixtures:
    source, audit = _load_docs_source(repo_root)
    docs_corpus = _derive_docs_corpus(source)
    return DerivedFixtures(
        extract_urls=_derive_extract_cases(repo_root, source),
        web_search_queries=_derive_web_cases(source),
        docs_recall_cases=_derive_docs_cases(source, docs_corpus),
        docs_corpus=docs_corpus,
        source_audit=audit,
    )


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return ("".join(_canonical_json(record) + "\n" for record in records)).encode(
        "utf-8"
    )


def render_fixture_files(derived: DerivedFixtures, repo_root: Path) -> dict[str, bytes]:
    payload_files = {
        FIXTURE_FILES["extract_urls"]: _jsonl_bytes(derived.extract_urls),
        FIXTURE_FILES["web_search_queries"]: _jsonl_bytes(derived.web_search_queries),
        FIXTURE_FILES["docs_recall_cases"]: _jsonl_bytes(derived.docs_recall_cases),
        FIXTURE_FILES["docs_corpus"]: _jsonl_bytes(derived.docs_corpus),
    }
    source_hashes = {path: _sha256_file(repo_root / path) for path in SOURCE_PATHS}
    manifest = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "fixture_version": "v1",
        "immutable": True,
        "counts": TARGET_COUNTS,
        "source_audit": derived.source_audit,
        "source_sha256": source_hashes,
        "payload_sha256": {
            name: _sha256_bytes(content) for name, content in payload_files.items()
        },
        "thresholds": THRESHOLDS,
        "derivation": {
            "duplicates": "exclude every conflicting source ID before sampling",
            "selection": "ascending SHA-256(source ID), then source ID",
            "web_labels": "library term plus at least two distinct intent terms",
            "docs_labels": "expected stable chunk ID from deduplicated corpus",
            "extract_urls": "literal repo URLs then canonical registry URLs",
        },
    }
    provenance = (
        b"wet-mcp benchmark fixture v1\n"
        b"============================\n"
        b"\n"
        b"This directory is immutable. Create v2 instead of editing v1 in place.\n"
        b"All records are mechanically derived from versioned repository sources.\n"
        b"The 2,000-case docs source contains 42 conflicting duplicate IDs; every\n"
        b"record carrying one of those IDs is excluded, leaving 1,916 unambiguous\n"
        b"records. Web and docs evaluation cases are selected by SHA-256(source ID).\n"
        b"No benchmark result or measured metric is stored in these fixtures.\n"
        b"Regenerate/check with:\n"
        b"  uv run python tests/search_quality/run_contract.py generate-fixtures --check\n"
    )
    return {
        **payload_files,
        "manifest.jsonl": _jsonl_bytes([manifest]),
        "PROVENANCE.txt": provenance,
    }


def write_fixture_files(
    repo_root: Path, fixture_root: Path = DEFAULT_FIXTURE_ROOT
) -> dict[str, str]:
    rendered = render_fixture_files(derive_fixture_records(repo_root), repo_root)
    fixture_root.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        (fixture_root / name).write_bytes(content)
    return {name: _sha256_bytes(content) for name, content in rendered.items()}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            raise ContractError(f"{path}:{line_number}: blank JSONL line")
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise ContractError(f"{path}:{line_number}: record must be an object")
        records.append(record)
    return records


def _require_record_base(record: dict[str, Any], suite: str, index: int) -> None:
    if record.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise ContractError(f"{suite}[{index}] has wrong schema_version")
    record_id = record.get("id")
    if not isinstance(record_id, str) or not _ID_RE.fullmatch(record_id):
        raise ContractError(f"{suite}[{index}] has invalid id")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        raise ContractError(f"{suite}[{index}] needs provenance")


def validate_fixture_set(fixture_root: Path = DEFAULT_FIXTURE_ROOT) -> dict[str, Any]:
    if not fixture_root.is_dir():
        raise ContractError(f"fixture directory missing: {fixture_root}")
    actual_files = {path.name for path in fixture_root.iterdir() if path.is_file()}
    if actual_files != REQUIRED_FILES:
        raise ContractError(
            f"fixture file set mismatch: expected {sorted(REQUIRED_FILES)}, "
            f"got {sorted(actual_files)}"
        )

    records_by_suite = {
        suite: load_jsonl(fixture_root / file_name)
        for suite, file_name in FIXTURE_FILES.items()
    }
    counts = {suite: len(records) for suite, records in records_by_suite.items()}
    if counts != TARGET_COUNTS:
        raise ContractError(
            f"fixture counts mismatch: expected {TARGET_COUNTS}, got {counts}"
        )

    all_ids: list[str] = []
    for suite, records in records_by_suite.items():
        for index, record in enumerate(records):
            _require_record_base(record, suite, index)
            all_ids.append(record["id"])
            if suite == "extract_urls":
                if urlsplit(str(record.get("url", ""))).scheme not in {"http", "https"}:
                    raise ContractError(f"{suite}[{index}] needs an HTTP(S) URL")
                if record.get("min_content_chars") != 80:
                    raise ContractError(f"{suite}[{index}] has wrong content threshold")
            elif suite == "web_search_queries":
                if not isinstance(record.get("query"), str) or not record["query"]:
                    raise ContractError(f"{suite}[{index}] needs query")
                if not record.get("library_terms"):
                    raise ContractError(f"{suite}[{index}] needs library_terms")
                intent_terms = record.get("intent_terms")
                if not isinstance(intent_terms, list) or len(intent_terms) < 2:
                    raise ContractError(f"{suite}[{index}] needs two intent terms")
                if record.get("min_intent_terms") != 2 or record.get("top_k") != 10:
                    raise ContractError(
                        f"{suite}[{index}] has wrong intent/rank contract"
                    )
            elif suite == "docs_recall_cases":
                expected = record.get("expected_chunk_ids")
                if not isinstance(expected, list) or not expected:
                    raise ContractError(f"{suite}[{index}] needs expected_chunk_ids")
                if record.get("top_k") != 10:
                    raise ContractError(f"{suite}[{index}] has wrong top_k")
            elif suite == "docs_corpus":
                for field in (
                    "chunk_id",
                    "library",
                    "version",
                    "url",
                    "title",
                    "content",
                ):
                    if not isinstance(record.get(field), str) or not record[field]:
                        raise ContractError(f"{suite}[{index}] needs {field}")

    if len(all_ids) != len(set(all_ids)):
        raise ContractError("fixture IDs must be globally unique")
    chunk_ids = [record["chunk_id"] for record in records_by_suite["docs_corpus"]]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ContractError("docs corpus chunk IDs must be unique")
    known_chunks = set(chunk_ids)
    for record in records_by_suite["docs_recall_cases"]:
        if not set(record["expected_chunk_ids"]).issubset(known_chunks):
            raise ContractError(f"{record['id']} references an unknown chunk")

    manifest_records = load_jsonl(fixture_root / "manifest.jsonl")
    if len(manifest_records) != 1:
        raise ContractError("manifest.jsonl must contain exactly one record")
    manifest = manifest_records[0]
    payload_hashes = {
        file_name: _sha256_file(fixture_root / file_name)
        for file_name in FIXTURE_FILES.values()
    }
    if manifest.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise ContractError("manifest schema_version mismatch")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ContractError("manifest contract_version mismatch")
    if manifest.get("immutable") is not True:
        raise ContractError("manifest must mark fixtures immutable")
    if manifest.get("counts") != TARGET_COUNTS:
        raise ContractError("manifest counts mismatch")
    if manifest.get("payload_sha256") != payload_hashes:
        raise ContractError("manifest payload hashes mismatch")
    if manifest.get("thresholds") != THRESHOLDS:
        raise ContractError("manifest thresholds mismatch")

    return {
        "fixture_version": "v1",
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "counts": counts,
        "sha256": {
            name: _sha256_file(fixture_root / name) for name in sorted(REQUIRED_FILES)
        },
    }


def _normalized_text(value: str) -> str:
    return " ".join(_tokens(value))


def _term_matches(term: str, text: str) -> bool:
    normalized_term = _normalized_text(term)
    return bool(normalized_term) and normalized_term in text


def _web_relevant(case: dict[str, Any], result: dict[str, Any]) -> bool:
    text = _normalized_text(
        " ".join(str(result.get(field, "")) for field in ("title", "snippet", "url"))
    )
    library_match = any(_term_matches(term, text) for term in case["library_terms"])
    intent_matches = sum(_term_matches(term, text) for term in case["intent_terms"])
    return library_match and intent_matches >= case["min_intent_terms"]


def score_web_case(
    case: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, float | int]:
    top_k = int(case.get("top_k", 10))
    relevance = [int(_web_relevant(case, result)) for result in results[:top_k]]
    hits = sum(relevance)
    dcg = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(relevance))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(hits))
    return {
        "hits_at_10": hits,
        "ndcg_at_10": dcg / ideal if ideal else 0.0,
    }


def percentile_nearest_rank(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires a non-empty sample")
    if not 0 < quantile <= 1:
        raise ValueError("quantile must be in (0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _tool_payload(result: Any) -> dict[str, Any]:
    for attribute in ("structuredContent", "structured_content"):
        value = getattr(result, attribute, None)
        if isinstance(value, dict):
            return value
    text = "".join(
        str(getattr(block, "text", "")) for block in getattr(result, "content", [])
    )
    wrapped = re.search(
        r"<untrusted_[^>]+>\s*(.*?)\s*</untrusted_[^>]+>", text, re.DOTALL
    )
    if wrapped:
        text = wrapped.group(1)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ContractError("MCP tool payload must be an object")
    return value


async def run_extract_case(
    session: ToolSession, case: dict[str, Any]
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await session.call_tool(
            "extract",
            {"action": "extract", "urls": [case["url"]], "format": "markdown"},
        )
        payload = _tool_payload(result)
        pages = payload.get("results", [])
        page = pages[0] if isinstance(pages, list) and pages else {}
        if not isinstance(page, dict):
            raise ContractError("extract result page must be an object")
        clean_text = str(page.get("clean_text") or page.get("content") or "")
        markdown = str(page.get("markdown") or page.get("content") or "")
        clean_chars = len("".join(clean_text.split()))
        markdown_chars = len("".join(markdown.split()))
        clean_ratio = min(1.0, clean_chars / max(markdown_chars, 1))
        success = (
            not payload.get("error")
            and not page.get("error")
            and (clean_chars >= int(case["min_content_chars"]))
        )
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": success,
            "clean_ratio": clean_ratio,
            "clean_pass": success and clean_ratio >= float(case["min_clean_ratio"]),
            "content_chars": clean_chars,
            **(
                {"error": str(payload.get("error") or page.get("error"))}
                if payload.get("error") or page.get("error")
                else {}
            ),
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": False,
            "clean_ratio": 0.0,
            "clean_pass": False,
            "content_chars": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run_web_case(session: ToolSession, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await session.call_tool(
            "search",
            {"action": "search", "query": case["query"], "max_results": 10},
        )
        payload = _tool_payload(result)
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list) or any(
            not isinstance(item, dict) for item in raw_results
        ):
            raise ContractError("search results must be a list of objects")
        score = score_web_case(case, raw_results)
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": not payload.get("error"),
            **score,
            **({"error": str(payload["error"])} if payload.get("error") else {}),
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": False,
            "hits_at_10": 0,
            "ndcg_at_10": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run_docs_case(session: ToolSession, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await session.call_tool(
            "search",
            {
                "action": "docs_query",
                "library": case["library"],
                "query": case["query"],
                "limit": 10,
            },
        )
        payload = _tool_payload(result)
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list) or any(
            not isinstance(item, dict) for item in raw_results
        ):
            raise ContractError("docs results must be a list of objects")
        returned_ids = {
            str(result.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
            for result in raw_results[:10]
        }
        expected_ids = set(case["expected_chunk_ids"])
        recall = len(returned_ids & expected_ids) / len(expected_ids)
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": not payload.get("error"),
            "recall_at_10": recall,
            **({"error": str(payload["error"])} if payload.get("error") else {}),
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "latency_ms": (time.perf_counter() - started) * 1000,
            "success": False,
            "recall_at_10": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def summarize_suite(suite: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ContractError(f"cannot summarize empty {suite} suite")
    latencies = [float(record["latency_ms"]) for record in records]
    metrics: dict[str, float] = {
        "p50_latency_ms": percentile_nearest_rank(latencies, 0.50),
        "p95_latency_ms": percentile_nearest_rank(latencies, 0.95),
        "success_rate": sum(bool(record["success"]) for record in records)
        / len(records),
    }
    if suite == "extract":
        metrics.update(
            {
                "clean_pass_rate": sum(bool(record["clean_pass"]) for record in records)
                / len(records),
                "mean_clean_ratio": sum(
                    float(record["clean_ratio"]) for record in records
                )
                / len(records),
            }
        )
    elif suite == "web_search":
        metrics.update(
            {
                "mean_hits_at_10": sum(int(record["hits_at_10"]) for record in records)
                / len(records),
                "mean_ndcg_at_10": sum(
                    float(record["ndcg_at_10"]) for record in records
                )
                / len(records),
            }
        )
    elif suite == "docs_recall":
        metrics["recall_at_10"] = sum(
            float(record["recall_at_10"]) for record in records
        ) / len(records)
    else:
        raise ContractError(f"unknown suite {suite}")
    return {"case_count": len(records), "metrics": metrics, "records": records}


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def build_provenance(
    repo_root: Path,
    *,
    fixture_proof: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    safe_config = {
        "search_backends": [
            item.strip()
            for item in os.environ.get(
                "SEARCH_BACKENDS", os.environ.get("SEARCH_BACKEND", "searxng")
            ).split(",")
            if item.strip()
        ],
        "rerank_provider": os.environ.get("RERANK_PROVIDER", "auto"),
        "docs_db_backend": os.environ.get("DOCS_DB_BACKEND", "sqlite"),
        "mcp_transport": "stdio",
    }
    for key, value in safe_config.items():
        if _SECRET_NAME_RE.search(key) or _SECRET_NAME_RE.search(str(value)):
            raise ContractError(f"unsafe provenance field: {key}")
    try:
        package_version = version("wet-mcp")
    except PackageNotFoundError:
        package_version = "source-checkout"
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "package_version": package_version,
        "safe_config": safe_config,
        "config_sha256": _sha256_bytes(_canonical_json(safe_config).encode("utf-8")),
    }
    return {
        "git": {
            "commit": _git(repo_root, "rev-parse", "HEAD"),
            "dirty": bool(_git(repo_root, "status", "--porcelain")),
        },
        "fixtures": fixture_proof,
        "protocol": {"client": "mcp.ClientSession", "transport": "stdio"},
        "command": command,
        "environment": environment,
    }


def build_artifact(
    *,
    provenance: dict[str, Any],
    suites: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected = {
        "extract": TARGET_COUNTS["extract_urls"],
        "web_search": TARGET_COUNTS["web_search_queries"],
        "docs_recall": TARGET_COUNTS["docs_recall_cases"],
    }
    complete = set(suites) == set(expected) and all(
        suites[name].get("case_count") == count for name, count in expected.items()
    )
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "complete": complete,
        "provenance": provenance,
        "suites": suites,
    }


def _require_number(value: Any, path: str) -> float:
    if value is None:
        raise ContractError(f"{path} must not be null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{path} must be numeric")
    if not math.isfinite(float(value)):
        raise ContractError(f"{path} must be finite")
    return float(value)


def validate_release_artifact(
    artifact: dict[str, Any],
    *,
    expected_commit: str,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> None:
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ContractError("artifact schema_version mismatch")
    if artifact.get("contract_version") != CONTRACT_VERSION:
        raise ContractError("artifact contract_version mismatch")
    if artifact.get("complete") is not True:
        raise ContractError("artifact must be complete")
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        raise ContractError("artifact provenance missing")
    git = provenance.get("git")
    if not isinstance(git, dict) or git.get("commit") != expected_commit:
        raise ContractError("artifact commit does not match release commit")
    if git.get("dirty") is not False:
        raise ContractError("release artifact must come from a clean checkout")
    if provenance.get("protocol") != {
        "client": "mcp.ClientSession",
        "transport": "stdio",
    }:
        raise ContractError("artifact protocol provenance mismatch")
    if provenance.get("fixtures") != validate_fixture_set(fixture_root):
        raise ContractError("artifact fixture hashes do not match checkout")
    environment = provenance.get("environment")
    if not isinstance(environment, dict) or not re.fullmatch(
        r"[0-9a-f]{64}", str(environment.get("config_sha256", ""))
    ):
        raise ContractError("artifact config provenance missing")
    if not isinstance(provenance.get("command"), list) or not provenance["command"]:
        raise ContractError("artifact command provenance missing")

    suites = artifact.get("suites")
    if not isinstance(suites, dict):
        raise ContractError("artifact suites missing")
    expected_counts = {
        "extract": TARGET_COUNTS["extract_urls"],
        "web_search": TARGET_COUNTS["web_search_queries"],
        "docs_recall": TARGET_COUNTS["docs_recall_cases"],
    }
    required_metrics = {
        "extract": (
            "p50_latency_ms",
            "p95_latency_ms",
            "success_rate",
            "clean_pass_rate",
            "mean_clean_ratio",
        ),
        "web_search": (
            "p50_latency_ms",
            "p95_latency_ms",
            "success_rate",
            "mean_hits_at_10",
            "mean_ndcg_at_10",
        ),
        "docs_recall": (
            "p50_latency_ms",
            "p95_latency_ms",
            "success_rate",
            "recall_at_10",
        ),
    }
    for suite_name, expected_count in expected_counts.items():
        suite = suites.get(suite_name)
        if not isinstance(suite, dict):
            raise ContractError(f"artifact suite missing: {suite_name}")
        if suite.get("case_count") != expected_count:
            raise ContractError(f"{suite_name} case_count must be {expected_count}")
        records = suite.get("records")
        if not isinstance(records, list) or len(records) != expected_count:
            raise ContractError(f"{suite_name} must retain every case record")
        record_ids = [
            record.get("id") for record in records if isinstance(record, dict)
        ]
        if len(record_ids) != expected_count or len(record_ids) != len(set(record_ids)):
            raise ContractError(f"{suite_name} records need unique IDs")
        metrics = suite.get("metrics")
        if not isinstance(metrics, dict):
            raise ContractError(f"{suite_name} metrics missing")
        for metric_name in required_metrics[suite_name]:
            _require_number(metrics.get(metric_name), f"{suite_name}.{metric_name}")

    extract_metrics = suites["extract"]["metrics"]
    web_metrics = suites["web_search"]["metrics"]
    docs_metrics = suites["docs_recall"]["metrics"]
    checks = (
        (
            _require_number(extract_metrics["success_rate"], "extract.success_rate")
            >= THRESHOLDS["extract"]["success_rate"],
            "extract success_rate",
        ),
        (
            _require_number(
                extract_metrics["clean_pass_rate"], "extract.clean_pass_rate"
            )
            >= THRESHOLDS["extract"]["clean_pass_rate"],
            "extract clean_pass_rate",
        ),
        (
            _require_number(
                extract_metrics["mean_clean_ratio"], "extract.mean_clean_ratio"
            )
            >= THRESHOLDS["extract"]["mean_clean_ratio"],
            "extract mean_clean_ratio",
        ),
        (
            _require_number(web_metrics["p95_latency_ms"], "web_search.p95_latency_ms")
            <= THRESHOLDS["web_search"]["p95_latency_ms_max"],
            "web_search p95_latency_ms",
        ),
        (
            _require_number(web_metrics["success_rate"], "web_search.success_rate")
            >= THRESHOLDS["web_search"]["success_rate"],
            "web_search success_rate",
        ),
        (
            _require_number(
                web_metrics["mean_hits_at_10"], "web_search.mean_hits_at_10"
            )
            >= THRESHOLDS["web_search"]["mean_hits_at_10"],
            "web_search mean_hits_at_10",
        ),
        (
            _require_number(
                web_metrics["mean_ndcg_at_10"], "web_search.mean_ndcg_at_10"
            )
            >= THRESHOLDS["web_search"]["mean_ndcg_at_10"],
            "web_search mean_ndcg_at_10",
        ),
        (
            _require_number(
                docs_metrics["p95_latency_ms"], "docs_recall.p95_latency_ms"
            )
            <= THRESHOLDS["docs_recall"]["p95_latency_ms_max"],
            "docs_recall p95_latency_ms",
        ),
        (
            _require_number(docs_metrics["success_rate"], "docs_recall.success_rate")
            >= THRESHOLDS["docs_recall"]["success_rate"],
            "docs_recall success_rate",
        ),
        (
            _require_number(docs_metrics["recall_at_10"], "docs_recall.recall_at_10")
            >= THRESHOLDS["docs_recall"]["recall_at_10"],
            "docs_recall recall_at_10",
        ),
    )
    failed = [name for passed, name in checks if not passed]
    if failed:
        raise ContractError("benchmark thresholds failed: " + ", ".join(failed))


def current_command() -> list[str]:
    return [sys.executable, *sys.argv]
