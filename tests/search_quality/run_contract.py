"""Generate, validate, execute, and gate wet's 200/500/200 benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import benchmark_contract as contract
import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parents[1]
# ``live_http`` is the merged wave-R8 HTTP spawn helper; run_contract executes
# as a script (CI calls it by path), so tests/ is not on sys.path there.
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from live_http import mcp_client_session, wet_http_server, wet_server_env  # noqa: E402

# The release gate injects exactly one real credential (OPENROUTER_API_KEY),
# so the web suite always measures the openrouter chain. One name, two uses:
# the spawned server's env and the backend recorded on the web_search suite.
WEB_SEARCH_BACKEND = "openrouter"

# The benchmark corpus is seeded WITHOUT vectors (fixture JSONL has no
# embeddings), so the benchmark server must answer docs_recall keyword-only.
# Two things make that deterministic on a box holding OPENROUTER_API_KEY:
# a config.toml that points the embed/rerank cells at a non-OpenRouter
# base_url (the OPENROUTER_API_KEY fallback only applies to the default
# base_url, so the cells stay unconfigured), and DISABLE_LOCAL_* suppressing
# the ONNX legs. Anything else lets a per-query cloud embed/rerank call into
# a suite whose thresholds assume local retrieval.
_BENCHMARK_CONFIG_TOML = """\
# Benchmark-isolated instance config: embed/rerank cells point at a
# non-OpenRouter base_url with no key, so the OPENROUTER_API_KEY fallback
# does NOT configure them — the spawned server stays keyword-only.
[models.embed]
base_url = "https://benchmark.invalid"

[models.rerank]
base_url = "https://benchmark.invalid"
"""

# Spend discipline during the run (incident 2026-10-11): the workflow's
# pre-flight only compares account credit against the cap once, before any
# call, and the run logged nothing about money while it spent for hours. The
# guard below measures this run's own spend (key usage now minus key usage at
# start), logs it, and aborts as soon as the cap is reached or the per-suite
# projection says it will be. Concurrent consumers of the same key inflate the
# delta, which errs toward stopping early, never toward overspending.
DEFAULT_SPEND_CAP_USD = 5.0
SPEND_CHECK_INTERVAL_S = 30.0
# Below this many finished cases a suite's per-case cost is too noisy to
# extrapolate from (one slow first search would abort a healthy run).
PROJECTION_MIN_CASES = 25
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
# Parallel web cases for LLM-mediated backends only: their p95 is reported but
# not gated (``contract.web_search_p95_threshold``), so contention cannot flip
# the gate, while 500 serial ~35 s searches alone took ~4.6 h of a 5 h job.
LLM_MEDIATED_WEB_CONCURRENCY = 4


class SpendCapExceeded(contract.ContractError):
    """Raised when this run reached, or is projected to exceed, its cap."""


@dataclass(frozen=True)
class KeyUsage:
    usage_usd: float
    limit_remaining_usd: float | None


@dataclass
class SpendGuard:
    cap_usd: float
    read_usage: Callable[[], Awaitable[KeyUsage]]
    clock: Callable[[], float] = time.monotonic
    log: Callable[[str], None] = field(
        default=lambda line: print(line, file=sys.stderr, flush=True)
    )
    _baseline_usd: float = field(default=0.0, init=False)
    _last_usd: float = field(default=0.0, init=False)
    _last_read_at: float = field(default=-math.inf, init=False)
    _suite_baseline_usd: dict[str, float] = field(default_factory=dict, init=False)

    @property
    def spent_usd(self) -> float:
        return self._last_usd - self._baseline_usd

    async def _read(self) -> float:
        reading = await self.read_usage()
        self._last_read_at = self.clock()
        self._last_usd = reading.usage_usd
        return reading.usage_usd

    async def start(self) -> None:
        reading = await self.read_usage()
        self._last_read_at = self.clock()
        self._baseline_usd = self._last_usd = reading.usage_usd
        remaining = reading.limit_remaining_usd
        self.log(
            f"spend guard: cap {self.cap_usd:.2f} USD; key usage at start "
            f"{reading.usage_usd:.2f} USD; key limit remaining "
            f"{'unlimited' if remaining is None else f'{remaining:.2f} USD'}"
        )
        if remaining is not None and remaining < self.cap_usd:
            raise SpendCapExceeded(
                f"key limit remaining {remaining:.2f} USD is below this run's "
                f"cap {self.cap_usd:.2f} USD; the run would die mid-suite with "
                "the money already spent. Raise the key limit or wait for its "
                "reset before dispatching."
            )

    async def check(
        self, suite: str, *, done: int, total: int, force: bool = False
    ) -> None:
        suite_baseline = self._suite_baseline_usd.setdefault(suite, self._last_usd)
        if not force and self.clock() - self._last_read_at < SPEND_CHECK_INTERVAL_S:
            return
        await self._read()
        spent = self.spent_usd
        projected = spent
        if done >= PROJECTION_MIN_CASES:
            per_case = (self._last_usd - suite_baseline) / done
            projected = spent + per_case * max(total - done, 0)
        self.log(
            f"spend guard: {suite} {done}/{total} cases, spent "
            f"{spent:.2f}/{self.cap_usd:.2f} USD, projected {projected:.2f} USD"
        )
        if spent >= self.cap_usd:
            raise SpendCapExceeded(
                f"run spent {spent:.2f} USD, reaching its cap "
                f"{self.cap_usd:.2f} USD, after {suite} {done}/{total}"
            )
        if projected > self.cap_usd:
            raise SpendCapExceeded(
                f"{suite} is projected to bring this run to {projected:.2f} USD, "
                f"over its cap {self.cap_usd:.2f} USD (spent {spent:.2f} USD "
                f"after {done}/{total} cases); stopping before the money is gone"
            )


def spend_cap_from_env(raw: str | None) -> float:
    """``OPENROUTER_SPEND_CAP_USD`` with the workflow's default for unset/blank."""
    if raw is None or not raw.strip():
        return DEFAULT_SPEND_CAP_USD
    try:
        cap = float(raw)
    except ValueError as exc:
        raise contract.ContractError(
            f"OPENROUTER_SPEND_CAP_USD must be a number, got {raw!r}"
        ) from exc
    if not math.isfinite(cap) or cap <= 0:
        raise contract.ContractError(
            f"OPENROUTER_SPEND_CAP_USD must be a positive finite number, got {raw!r}"
        )
    return cap


def openrouter_key_reader(api_key: str) -> Callable[[], Awaitable[KeyUsage]]:
    """Read this key's cumulative usage and remaining limit (never the key)."""

    async def read() -> KeyUsage:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {api_key}"}
            )
            response.raise_for_status()
        data = response.json()["data"]
        remaining = data.get("limit_remaining")
        return KeyUsage(
            usage_usd=float(data["usage"]),
            limit_remaining_usd=None if remaining is None else float(remaining),
        )

    return read


def _spend_guard_from_env() -> SpendGuard:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY is required: the spend guard measures this run's "
            "spend on the same key the benchmark server uses."
        )
    return SpendGuard(
        cap_usd=spend_cap_from_env(os.environ.get("OPENROUTER_SPEND_CAP_USD")),
        read_usage=openrouter_key_reader(api_key),
    )


def web_concurrency_for(backend: str) -> int:
    if backend in contract.LLM_MEDIATED_WEB_BACKENDS:
        return LLM_MEDIATED_WEB_CONCURRENCY
    return 1


async def run_cases_bounded[CaseT, ResultT](
    cases: list[CaseT],
    runner: Callable[[CaseT], Awaitable[ResultT]],
    *,
    concurrency: int,
    on_done: Callable[[int], Awaitable[None]],
) -> list[ResultT]:
    """Run ``cases`` with at most ``concurrency`` in flight, results in order.

    ``on_done`` sees the running completion count; when it raises (the spend
    guard), every in-flight and queued case is cancelled and that exception
    propagates unwrapped.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: list[Any] = [None] * len(cases)
    done = 0

    async def run_one(index: int, case: CaseT) -> None:
        nonlocal done
        async with semaphore:
            results[index] = await runner(case)
        done += 1
        await on_done(done)

    try:
        async with asyncio.TaskGroup() as group:
            for index, case in enumerate(cases):
                group.create_task(run_one(index, case))
    except ExceptionGroup as failures:
        raise failures.exceptions[0] from None
    return results


async def _run_suite(
    suite: str,
    cases: list[dict[str, Any]],
    runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    *,
    concurrency: int,
    guard: SpendGuard,
) -> list[dict[str, Any]]:
    total = len(cases)
    await guard.check(suite, done=0, total=total, force=True)

    async def on_done(done: int) -> None:
        await guard.check(suite, done=done, total=total, force=done == total)

    return await run_cases_bounded(
        cases, runner, concurrency=concurrency, on_done=on_done
    )


def _load_fixture_records() -> dict[str, list[dict[str, Any]]]:
    return {
        suite: contract.load_jsonl(contract.DEFAULT_FIXTURE_ROOT / file_name)
        for suite, file_name in contract.FIXTURE_FILES.items()
    }


def _server_embedding_identity(env: dict[str, str]) -> tuple[int, str]:
    """The (dims, model_identity) ``make_docs_db`` computes under ``env``.

    The benchmark config leaves [models.embed] unconfigured by construction
    (see ``_BENCHMARK_CONFIG_TOML``), so the identity is the local embedding
    model resolution: ``LOCAL_EMBEDDING_MODEL`` verbatim, else the bundled
    ONNX default — mirroring ``Settings.resolve_local_embedding_model``.
    """
    from wet.runtime import DEFAULT_EMBEDDING_DIMS

    dims = int(env.get("EMBEDDING_DIMS") or "0") or DEFAULT_EMBEDDING_DIMS
    model = env.get("LOCAL_EMBEDDING_MODEL") or "n24q02m/Qwen3-Embedding-0.6B-ONNX"
    return dims, model


def _seed_docs_database(
    path: Path,
    corpus: list[dict[str, Any]],
    *,
    embedding_dims: int = 0,
    model_identity: str = "",
) -> None:
    """Materialize the versioned controlled corpus before protocol execution.

    ``embedding_dims``/``model_identity`` must match what the spawned
    server's ``make_docs_db`` computes for the same store — the B2 identity
    guard refuses to open a store stamped with a different embedding
    identity (``EmbeddingModelMismatch``).
    """
    from wet.db import DocsDB

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in corpus:
        grouped[record["library"]].append(record)

    database = DocsDB(
        path, embedding_dims=embedding_dims, model_identity=model_identity
    )
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


def _require_openrouter_model() -> str:
    """Return the explicitly-provided benchmark model, or fail loudly.

    The benchmark makes ~200 paid chat completions, each carrying the
    ``openrouter:web_search`` server tool whose fetched results are injected
    into context — spend scales with model price × injected-context volume.
    A silent default therefore spends real credit on an unapproved model,
    which is exactly what the 2026-10-05 incident did. Model choice is a
    user decision, never a harness default.
    """
    model = os.environ.get("OPENROUTER_MODEL", "").strip()
    if not model:
        raise SystemExit(
            "OPENROUTER_MODEL is required and has no default: the benchmark "
            "never picks a paid model silently. Set the env (local) or the "
            "vars.OPENROUTER_MODEL repo variable (CI) to a user-approved "
            "OpenRouter slug."
        )
    return model


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
            "SEARCH_BACKENDS": WEB_SEARCH_BACKEND,
            # Spend discipline (user directive 2026-10-05, after a benchmark
            # run silently burned $5.17 on a paid slug): there is NO default
            # model. The model is the user's decision — benchmark.yml reads
            # vars.OPENROUTER_MODEL and fails fast when unset; local runs
            # must set the env explicitly.
            "OPENROUTER_MODEL": _require_openrouter_model(),
            # Drive is no longer a wet storage backend. Blank stale local
            # OAuth values so they cannot change this isolated protocol
            # benchmark.
            "GOOGLE_DRIVE_CLIENT_ID": "",
            "GOOGLE_DRIVE_CLIENT_SECRET": "",
            # Deterministic keyword-only docs suite (see
            # ``_BENCHMARK_CONFIG_TOML``): no embed/rerank leg may resolve.
            # Env-key blanks beat config.toml api_key fields; the custom
            # base_url in the config beats the OPENROUTER_API_KEY fallback.
            "HULL_EMBED_API_KEY": "",
            "HULL_RERANK_API_KEY": "",
            "DISABLE_LOCAL_EMBED": "true",
            "DISABLE_LOCAL_RERANK": "true",
            # Pin identity inputs so seed and server stamp the same
            # (dims, model) regardless of host env/GPU.
            "EMBEDDING_DIMS": "768",
            "LOCAL_EMBEDDING_MODEL": "n24q02m/Qwen3-Embedding-0.6B-ONNX",
            # Fail closed on any residual identity drift rather than
            # silently reindexing the seeded store (a developer's
            # REINDEX_ON_MODEL_CHANGE=true user env masked this bug
            # locally while CI failed).
            "REINDEX_ON_MODEL_CHANGE": "false",
        }
    )
    return env


def _write_benchmark_config(env: dict[str, str]) -> None:
    """Drop the isolated config.toml into the spawned server's tmp home."""
    home = Path(env["HOME"])  # ``wet_server_env`` points every home var here.
    config_dir = home / ".wet"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(_BENCHMARK_CONFIG_TOML, encoding="utf-8")


async def _run_protocol(
    fixtures: dict[str, list[dict[str, Any]]],
    *,
    smoke_limit: int | None,
    guard: SpendGuard,
) -> dict[str, dict[str, Any]]:
    # Before the server spawns or any case runs: a key that cannot cover the
    # cap fails here with nothing spent.
    await guard.start()
    web_concurrency = web_concurrency_for(WEB_SEARCH_BACKEND)
    # mkdtemp + manual rmtree instead of TemporaryDirectory: on Windows the
    # spawned server's LifecycleLock byte-range lock can outlive
    # proc.terminate() by a beat, and a single rmtree then loses to
    # WinError 32. Retrying absorbs the OS handle-teardown window.
    temp_root = Path(tempfile.mkdtemp(prefix="wet-benchmark-v1-"))
    try:
        docs_db_path = temp_root / "docs.db"
        env = _server_environment(temp_root, docs_db_path)
        _write_benchmark_config(env)
        dims, model_identity = _server_embedding_identity(env)
        _seed_docs_database(
            docs_db_path,
            fixtures["docs_corpus"],
            embedding_dims=dims,
            model_identity=model_identity,
        )
        async with wet_http_server(
            env,
            temp_root / "server.log",
        ) as port:
            async with mcp_client_session(port, timeout=600.0) as session:
                await session.initialize()
                extract_cases = fixtures["extract_urls"][:smoke_limit]
                web_cases = fixtures["web_search_queries"][:smoke_limit]
                docs_cases = fixtures["docs_recall_cases"][:smoke_limit]
                # Serial on purpose: extract hits real sites whose anti-bot
                # response concurrency would change, and docs_recall's p95 is
                # gated.
                extract_records = await _run_suite(
                    "extract",
                    extract_cases,
                    lambda case: contract.run_extract_case(session, case),
                    concurrency=1,
                    guard=guard,
                )
                web_records = await _run_suite(
                    "web_search",
                    web_cases,
                    lambda case: contract.run_web_case(session, case),
                    concurrency=web_concurrency,
                    guard=guard,
                )
                docs_records = await _run_suite(
                    "docs_recall",
                    docs_cases,
                    lambda case: contract.run_docs_case(session, case),
                    concurrency=1,
                    guard=guard,
                )
    finally:
        _remove_tree(temp_root)

    web_summary = contract.summarize_suite("web_search", web_records)
    # Record the measured backend so the gate can pick the effective p95
    # bound (see contract.web_search_p95_threshold), and the concurrency the
    # reported (ungated) p95 was measured under.
    web_summary["backend"] = WEB_SEARCH_BACKEND
    web_summary["concurrency"] = web_concurrency
    return {
        "extract": contract.summarize_suite("extract", extract_records),
        "web_search": web_summary,
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
            suites = asyncio.run(
                _run_protocol(
                    fixtures,
                    smoke_limit=args.smoke_limit,
                    guard=_spend_guard_from_env(),
                )
            )
            result = contract.build_artifact(provenance=provenance, suites=suites)
            result["generated_at"] = datetime.now(UTC).isoformat()
            _write_json(args.output, result)
        else:
            artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
            if not isinstance(artifact, dict):
                raise contract.ContractError("artifact must be a JSON object")
            warnings = contract.validate_release_artifact(
                artifact,
                expected_commit=args.expected_commit,
                fixture_root=contract.DEFAULT_FIXTURE_ROOT,
            )
            result = {
                "status": "pass",
                "artifact": str(args.artifact),
                "expected_commit": args.expected_commit,
                "warnings": warnings,
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark contract failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
