# wet Benchmarks

> v2.0.0: `extract.agent` + `extract.interact` shipped (BREAKING).

This document captures the historical v1.x baseline and the live W11 baseline
in `docs/benchmarks/v2_w11_baseline.json` (replacing all May 2026 `null`
placeholders).

## v2 W11 baseline (2026-11-27)

Recorded in `docs/benchmarks/v2_w11_baseline.json` (superseding
`docs/benchmarks/v1_phase2_baseline.json`) via real streamable-HTTP MCP protocol
calls (`ClientSession` -> spawned `python -m wet.server`) against `v2` fixtures
(`1916` corpus records, `200` docs recall cases, `50` web search queries on
`tavily`, `50` extract URLs) plus the full `pytest --cov=wet` suite:

| Pillar | Metric | Measured | Target | Method |
|---|---|---|---|---|
| Coverage | `pytest --cov=wet` | 95.50% | >= 95% | `uv run pytest --cov=wet --cov-fail-under=95` (2286 passed, 32 skipped, 94 deselected, 280.7s) |
| Web Search | `search_p95_ms` | 614.94 ms | < 2000 ms | 50 queries (`tavily`), p50 = 409.45 ms, throughput = 4.35 qps, success = 98.0%, hits@10 = 9.42, nDCG@10 = 0.964 |
| Extract | `extract_tier1_success_rate` | 0.98 (98.0%) | >= 0.95 | 50 URLs (`v2/extract_urls.jsonl`), p50 = 2643.30 ms, p95 = 7757.61 ms, 1.65 urls/s, mean clean ratio = 0.5213 |
| Docs Query | `docs_query_p95_ms` | 41.74 ms | < 500 ms | 200 cases (`v2/docs_recall_cases.jsonl`), p50 = 29.11 ms, throughput = 125.46 qps |
| Docs Quality | `docs_query_recall_at_10` | 1.00 | >= 0.85 | 200 cases seeded from `v2/docs_corpus.jsonl`, success = 100% |
| Startup | `startup_time_ms` | 9254.15 ms | < 1000 ms warm | Cold Windows subprocess spawn -> `/mcp` HTTP up (`9135.4 ms`) + `initialize()` + `list_tools()` |
| Memory | `rss_steady_mb` | 399.72 MB | < 400 MB | Process-tree RSS after workload (`rss_idle_mb` = 238.68 MB) |

Reproduce end-to-end (with `0` `null` fields):

```bash
skret run -e prod -- uv run python scripts/run_w11_baseline.py
```

Pass `--extract-limit 200 --web-limit 500 --docs-limit 200` for the full 200/500/200 fixture sweep.

## W5 quality corpus and runner (2026-08-22)

The repeatable public-safe corpus is
`tests/fixtures/benchmark/wet-quality-corpus.jsonl`. It records a stable
corpus ID, query, source URL, expected result type and fields, judged
relevance metadata, freshness class, and provenance. It contains no private
pages, credentials, or user content.

Run the local direct benchmark from the repository root:

```bash
uv run python scripts/benchmark_quality.py \
  --corpus tests/fixtures/benchmark/wet-quality-corpus.jsonl \
  --mode stdio \
  --backend searxng \
  --output-jsonl /path/to/wet-benchmark.jsonl \
  --output-summary /path/to/wet-benchmark-summary.json
```

`--mode stdio` is a historical flag name: wet no longer has a stdio transport
(the server is HTTP-only). In this runner the mode means a direct, in-process
call of the `search` / `extract` tool functions from `wet.server`, with no MCP
transport and no running server. It measures the tool logic and the backend
chain, not the protocol path. `--backend searxng` needs a working SearXNG (an
auto-started instance, or `SEARXNG_URL`); without one every `search` case ends
as `EMPTY_RESULTS` and the run exits 1. `docs` cases resolve against the local
docs store and need no search backend.

The JSONL output contains one machine-readable result per corpus item followed
by one `record_type=aggregate` row. Per-item records include coverage,
judged-relevance precision, latency, cost estimate plus `cost_basis`, failure
class, and an extraction round-trip hash. A cost estimate is emitted only for
an observed/known-cost request; failed or unobserved provider work is marked
`not_attempted` or `usage_unavailable` rather than assigned a hypothetical
charge. `--mode hosted` fails closed in this direct runner
(`UNSUPPORTED_MODE`); it must not be reported as a local direct-call
measurement.

Run the protocol-level benchmark through the real HTTP transport instead. It
spawns the production server (`python -m wet.server`) on a loopback port and
drives it with a streamable-HTTP `ClientSession`:

```bash
uv run python tests/search_quality/run_contract.py validate-fixtures
uv run python tests/search_quality/run_contract.py run --output /path/to/wet-benchmark-contract.json
```

This is the harness the `benchmark` job of `ci.yml` runs (dispatch `ci.yml`
with `job=benchmark`). Credentials come from
the environment and are never printed or persisted.

## v1.x baseline (2026-05-09)

| Pillar | Metric | Value | Method |
|---|---|---|---|
| Coverage | `pytest --cov` | 93.24% | CI gate currently 93%, long-term target 95% |
| Test suite | Total tests passed | 1606 | `uv run pytest` (unit + integration; e2e + benchmark + live excluded) |
| Test suite | Total tests skipped | 34 | Skips driven by missing optional creds (cloud APIs) |
| Tier-1 extract | Sample fixture size | 20 URLs | Sampled subset; full 200 URL fixture pending pre-release run |
| Tier-1 extract | Success rate (sample) | >=80% | Target 95% on full 200 URL fixture |

## Latency placeholders

Real measurements land in the pre-release benchmark CI run. Targets:

| Pillar | Metric | Target | Methodology |
|---|---|---|---|
| Search | Query p95 (query -> embed rerank -> return) | < 2 s | 500 diverse queries fixture |
| Extract | Tier-1 success rate | >= 95% | 200 URL fixture, diverse domains |
| Extract | Tier-2 (Cloudflare/captcha) success rate | >= 70% with CapSolver / >= 50% without | 50 defended-site URL fixture |
| Extract | Markdown clean ratio (content/total chars) | >= 0.70 | 100 news/blog fixture, manual ground truth |
| Overall | Startup time (warm cache) | < 1 s | `uv run` -> first MCP initialize |
| Overall | Memory footprint (idle server) | < 400 MB | RSS after startup + 10 tool calls |
| Overall | Test coverage | >= 95% | `pytest --cov-fail-under=95` enforced in CI |

## Baseline gate notes

- **Coverage gate**: CI currently enforces `--cov-fail-under=93`. The
  `>=95%` target unlocks once the 200-URL tier-1 fixture is finalized
  and exercised by the integration suite.
- **Tier-1 fixture**: 20-URL sample committed. Full 200-URL fixture
  deferred to a pre-release benchmark session.
- **Search polish**: query expansion + TTL cache (3600 s general / 300 s
  time-sensitive) + standardized citation format + 200-token snippet
  cap.
- **ScrapingAgent migration**: extract pipeline backed by
  `n24q02m-web-core` `ScrapingAgent` 5-strategy chain. Markdown output
  comparable to prior Crawl4AI-direct config across the sample fixture;
  full A/B comparison runs in a pre-release benchmark session.
- **Media slim**: `media.analyze` removed in v2.0.0; use
  `imagine-mcp.understand`. `list` + `download` unchanged.

## Pre-release benchmark plan

The pre-release benchmark CI job runs:

1. `tests/fixtures/urls/tier1_popular/` (200 URLs across diverse popular
   domains) -- success rate + markdown clean ratio.
2. `tests/fixtures/urls/tier2_defended/` (50 Cloudflare/captcha URLs) --
   success rate with and without CapSolver.
3. `tests/fixtures/queries/search_general/` (500 queries) -- p95 latency
   and recall@10 against curated ground truth.
4. `tests/fixtures/queries/search_time_sensitive/` (50 "today/latest"
   queries) -- freshness metric.
5. Startup time + idle memory snapshot.

Results write to `tests/fixtures/benchmarks/history/<timestamp>.json` and
get diff'd against the previous run for regression alerting.

## Docs search targets

| Pillar | Metric | Target | Methodology |
|---|---|---|---|
| Docs | `docs_resolve` + `docs_query` p95 | < 500 ms | 500 popular library queries |
| Docs | Recall@10 (correct lib + correct version chunks) | >= 0.85 | 200 (library, question, expected_chunks) eval set |
| Docs | Index freshness (Tier 1 / Tier 2 within 7-day lag) | >= 90% Tier 1 / >= 70% Tier 2 | `refresh-tier1` CI job (dispatch `ci.yml` with `job=refresh-tier1`) |
| Docs | Token cap per response | <= 5000 tokens | Greedy accumulator in `query_docs` |

The docs-search pillar ships the schema + dispatchers; the 200-fixture
recall eval and 500-query latency run land in a consolidated pre-release
session.

## Agent + interact targets

| Pillar | Metric | Target | Methodology |
|---|---|---|---|
| extract.agent | End-to-end p95 (5-URL synthesis) | < 30 s | 50 research-style queries fixture |
| extract.agent | Synthesis quality (1-5 manual rubric) | mean >= 4.0 | 50-query fixture with curated ground truth |
| extract.interact | Per-action p95 latency | < 5 s | 20 fixture flows (login, search, submit) |
| extract.interact | Session reuse hit rate | >= 90% on 2nd call | 10 multi-step flows |
| Overall regression | Regression vs `v1_phase2_baseline` | within +/- 10% | `docs/benchmarks/v1_phase2_baseline.json` |

Live latency runs land in a consolidated pre-release session. Until
then, baseline values are captured in
`docs/benchmarks/v1_phase2_baseline.json` (`v2.31.0-beta.1`) so deltas
can be computed deterministically.

### Coverage gate

- Baseline: 95.50% measured in `docs/benchmarks/v2_w11_baseline.json`
  (CI/local gate `--cov-fail-under=95` enforced in `pyproject.toml`).

## Cross-references

- Architecture: `docs/ARCHITECTURE.md`
- Migration guide: `docs/migration.md` (v1.x.y -> v2.0.0)
