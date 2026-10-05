"""Generate, validate, execute, and gate wet's 200/500/200 benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import benchmark_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parents[1]
# ``live_http`` is the merged wave-R8 HTTP spawn helper; run_contract executes
# as a script (CI calls it by path), so tests/ is not on sys.path there.
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from live_http import mcp_client_session, wet_http_server, wet_server_env  # noqa: E402


def _load_fixture_records() -> dict[str, list[dict[str, Any]]]:
    return {
        suite: contract.load_jsonl(contract.DEFAULT_FIXTURE_ROOT / file_name)
        for suite, file_name in contract.FIXTURE_FILES.items()
    }


def _seed_docs_database(path: Path, corpus: list[dict[str, Any]]) -> None:
    """Materialize the versioned controlled corpus before protocol execution."""
    from wet.db import DocsDB

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in corpus:
        grouped[record["library"]].append(record)

    database = DocsDB(path, embedding_dims=0)
    try:
        for library in sorted(grouped):
            records = grouped[library]
            library_id = database.upsert_library(
                name=library,
                canonical_name=library,
                docs_url=f"https://benchmark.invalid/library/{records[0]['id']}",
                registry="benchmark-v1",
                description="Controlled wet benchmark fixture",
            )
            version_id = database.upsert_version(
                library_id=library_id,
                version="benchmark-v1",
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
                    "section": "benchmark-v1",
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


def _server_environment(temp_root: Path, docs_db_path: Path) -> dict[str, str]:
    """Benchmark server env: wave-R8 isolation plus the seeded corpus paths."""
    env = wet_server_env(temp_root)
    env.update(
        {
            "CACHE_DIR": str(temp_root / "cache"),
            "DOCS_DB_BACKEND": "sqlite",
            "DOCS_DB_PATH": str(docs_db_path),
            "WET_DOCS_DB_PATH": str(docs_db_path),
            "DOWNLOAD_DIR": str(temp_root / "downloads"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "WARNING"),
            # The release gate injects exactly one real credential —
            # OPENROUTER_API_KEY — so the web suite runs the openrouter
            # backend chain; the default searxng chain cannot exist in CI.
            "SEARCH_BACKENDS": "openrouter",
            # The repo default ":free" slug 404s upstream (dropped from the
            # free tier); pin the paid slug the same key actually serves.
            "OPENROUTER_MODEL": os.environ.get(
                "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"
            ),
            # Drive is no longer a wet storage backend. Blank stale local
            # OAuth values so they cannot change this isolated protocol
            # benchmark.
            "GOOGLE_DRIVE_CLIENT_ID": "",
            "GOOGLE_DRIVE_CLIENT_SECRET": "",
        }
    )
    return env


async def _run_protocol(
    fixtures: dict[str, list[dict[str, Any]]],
    *,
    smoke_limit: int | None,
) -> dict[str, dict[str, Any]]:
    # mkdtemp + manual rmtree instead of TemporaryDirectory: on Windows the
    # spawned server's LifecycleLock byte-range lock can outlive
    # proc.terminate() by a beat, and a single rmtree then loses to
    # WinError 32. Retrying absorbs the OS handle-teardown window.
    temp_root = Path(tempfile.mkdtemp(prefix="wet-benchmark-v1-"))
    try:
        docs_db_path = temp_root / "docs.db"
        _seed_docs_database(docs_db_path, fixtures["docs_corpus"])
        async with wet_http_server(
            _server_environment(temp_root, docs_db_path),
            temp_root / "server.log",
        ) as port:
            async with mcp_client_session(port, timeout=600.0) as session:
                await session.initialize()
                extract_cases = fixtures["extract_urls"][:smoke_limit]
                web_cases = fixtures["web_search_queries"][:smoke_limit]
                docs_cases = fixtures["docs_recall_cases"][:smoke_limit]
                extract_records = [
                    await contract.run_extract_case(session, case)
                    for case in extract_cases
                ]
                web_records = [
                    await contract.run_web_case(session, case) for case in web_cases
                ]
                docs_records = [
                    await contract.run_docs_case(session, case) for case in docs_cases
                ]
    finally:
        _remove_tree(temp_root)

    return {
        "extract": contract.summarize_suite("extract", extract_records),
        "web_search": contract.summarize_suite("web_search", web_records),
        "docs_recall": contract.summarize_suite("docs_recall", docs_records),
    }


def _remove_tree(root: Path, *, attempts: int = 10) -> None:
    for attempt in range(attempts):
        try:
            shutil.rmtree(root)
            return
        except OSError:
            if attempt == attempts - 1:
                # Cleanup must never mask the measured protocol result.
                shutil.rmtree(root, ignore_errors=True)
                return
            time.sleep(0.5)


def _check_generated() -> None:
    expected = contract.render_fixture_files(
        contract.derive_fixture_records(REPO_ROOT), REPO_ROOT
    )
    root = contract.DEFAULT_FIXTURE_ROOT
    actual_names = {path.name for path in root.iterdir()} if root.is_dir() else set()
    if actual_names != set(expected):
        raise contract.ContractError(
            f"generated fixture file set differs: expected {sorted(expected)}, "
            f"got {sorted(actual_names)}"
        )
    changed = [
        name
        for name, content in expected.items()
        if (root / name).read_bytes() != content
    ]
    if changed:
        raise contract.ContractError(
            "immutable fixture derivation differs: " + ", ".join(sorted(changed))
        )


def _generate_fixtures(*, check: bool) -> dict[str, Any]:
    if check:
        _check_generated()
    else:
        rendered = contract.render_fixture_files(
            contract.derive_fixture_records(REPO_ROOT), REPO_ROOT
        )
        root = contract.DEFAULT_FIXTURE_ROOT
        if root.exists():
            existing = {path.name: path.read_bytes() for path in root.iterdir()}
            if existing and existing != rendered:
                raise contract.ContractError(
                    "v1 is immutable and differs from derivation; create v2"
                )
        root.mkdir(parents=True, exist_ok=True)
        for name, content in rendered.items():
            (root / name).write_bytes(content)
    return contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    generate = subcommands.add_parser("generate-fixtures")
    generate.add_argument("--check", action="store_true")

    subcommands.add_parser("validate-fixtures")

    run = subcommands.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--smoke-limit",
        type=int,
        help="Run this many cases per suite; artifact is intentionally incomplete.",
    )

    gate = subcommands.add_parser("gate")
    gate.add_argument("--artifact", type=Path, required=True)
    gate.add_argument("--expected-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate-fixtures":
            result = _generate_fixtures(check=args.check)
        elif args.command == "validate-fixtures":
            result = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)
        elif args.command == "run":
            if args.smoke_limit is not None and args.smoke_limit < 1:
                raise contract.ContractError("--smoke-limit must be positive")
            fixture_proof = contract.validate_fixture_set(contract.DEFAULT_FIXTURE_ROOT)
            fixtures = _load_fixture_records()
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                *(argv or sys.argv[1:]),
            ]
            provenance = contract.build_provenance(
                REPO_ROOT,
                fixture_proof=fixture_proof,
                command=command,
            )
            suites = asyncio.run(_run_protocol(fixtures, smoke_limit=args.smoke_limit))
            result = contract.build_artifact(provenance=provenance, suites=suites)
            result["generated_at"] = datetime.now(UTC).isoformat()
            _write_json(args.output, result)
        else:
            artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
            if not isinstance(artifact, dict):
                raise contract.ContractError("artifact must be a JSON object")
            contract.validate_release_artifact(
                artifact,
                expected_commit=args.expected_commit,
                fixture_root=contract.DEFAULT_FIXTURE_ROOT,
            )
            result = {
                "status": "pass",
                "artifact": str(args.artifact),
                "expected_commit": args.expected_commit,
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark contract failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
