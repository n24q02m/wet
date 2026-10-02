# wet-mcp Benchmarks

> v2.0.0: `extract.agent` + `extract.interact` shipped (BREAKING).

This document captures the v1.x baseline metrics. Full pre-release
benchmark runs (latency p50 / p95, recall@10, freshness, success rate
against the 200-URL tier-1 fixture) land in a pre-release benchmark
session.

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

The JSONL output contains one machine-readable result per corpus item followed
by one `record_type=aggregate` row. Per-item records include coverage,
judged-relevance precision, latency, cost estimate plus `cost_basis`, failure
class, and an extraction round-trip hash. A cost estimate is emitted only for
an observed/known-cost request; failed or unobserved provider work is marked
`not_attempted` or `usage_unavailable` rather than assigned a hypothetical
charge. Hosted and local-relay modes fail closed in this direct runner; those
modes require the authorized MCP protocol harness and must not be reported as
local direct-call measurements.

Run the hosted representative path through the MCP protocol harness instead:

```bash
uv run python scripts/cf_full_flow.py --endpoint https://<your-worker-domain>
```

The harness obtains an authorized session from environment-provided credentials,
opens a Streamable HTTP `ClientSession`, and requires both a real search result
and non-empty extracted page content. It does not print or persist credentials.

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
| Docs | Index freshness (Tier 1 / Tier 2 within 7-day lag) | >= 90% Tier 1 / >= 70% Tier 2 | Weekly `refresh-tier1` cron job |
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

- Current baseline: 92% (CI gate `--cov-fail-under=92`).
- Target: maintain >= 92%, climb back to >= 95% in a consolidated
  coverage push.

## Cross-references

- Architecture: `docs/ARCHITECTURE.md`
- Migration guide: `docs/migration.md` (v1.x.y -> v2.0.0)
