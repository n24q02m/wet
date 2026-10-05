"""jev advisory placements (spec 2026-09-26 §7): K1 HyDE gate + N6 refine stop.

Covers:
- the shared scorer parser contract (first-float extraction, raise on
  empty/non-numeric — the mnemo N1 shape, never a silent neutral score);
- ``results_sufficient`` fail-open: unconfigured cell, provider error, or
  non-numeric answer → ``None`` with metrics attempt totals still recorded;
- K1: a "sufficient" verdict skips the docs HyDE strategy round and ships
  a ``jev`` receipt block; insufficient/failed jev keeps the exact baseline
  payload (fail-open);
- N6: a "sufficient" verdict stops the refine loop before the rewrite
  round; failed jev keeps the exact baseline refine behavior;
- the client contract pinned on the cell call: temperature 0,
  ``max_tokens=1024``, ``reasoning={"exclude": True}`` (glm reasoning on
  OpenRouter eats the budget otherwise).
"""

import json
import unittest.mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from structured import payload

from wet import search_metrics
from wet.jev import parse_score, results_sufficient

# ---------------------------------------------------------------------------
# Parser contract (raise on non-numeric, never silent 0.5)
# ---------------------------------------------------------------------------


def test_parse_score_extracts_first_number_from_prose():
    assert parse_score("sufficiency: 0.8") == 0.8
    assert parse_score("0.42 — the results are partial") == 0.42
    assert parse_score("0") == 0.0


def test_parse_score_clamps_to_unit_interval():
    assert parse_score("2.5") == 1.0
    assert parse_score("-3") == 0.0


def test_parse_score_raises_on_empty():
    with pytest.raises(ValueError, match="empty completion"):
        parse_score("   ")


def test_parse_score_raises_on_non_numeric():
    with pytest.raises(ValueError, match="no numeric score"):
        parse_score("The results look fine to me.")


# ---------------------------------------------------------------------------
# results_sufficient: numeric path + fail-open paths
# ---------------------------------------------------------------------------


def _patch_cell(monkeypatch, *, configured=True, text=None, error=None):
    """Patch the ``jev_score`` cell in wet.runtime; records chat kwargs."""
    from wet import runtime

    seen: dict = {}

    class _Cell:
        async def chat(self, messages, **kwargs):
            seen.update(kwargs)
            seen["messages"] = messages
            if error is not None:
                raise error
            return text

    monkeypatch.setattr(
        runtime, "cell_configured", lambda task, settings=None: configured
    )
    monkeypatch.setattr(
        runtime,
        "provider_client",
        lambda task, settings=None, **kw: _Cell(),
    )
    return seen


async def test_results_sufficient_returns_score_and_records_metrics(monkeypatch):
    seen = _patch_cell(monkeypatch, text="sufficiency: 0.9")
    before = search_metrics.query_count("jev_score")

    score = await results_sufficient("q", [{"title": "T", "snippet": "s"}])

    assert score == 0.9
    assert search_metrics.query_count("jev_score") == before + 1
    assert search_metrics.latency_ema("jev_score") is not None
    # Client contract (mnemo N1 shape): budgeted, reasoning excluded.
    assert seen["max_tokens"] == 1024
    assert seen["temperature"] == 0
    assert seen["reasoning"] == {"exclude": True}


async def test_results_sufficient_fail_open_when_unconfigured(monkeypatch):
    _patch_cell(monkeypatch, configured=False)

    assert await results_sufficient("q", []) is None


async def test_results_sufficient_fail_open_on_provider_error(monkeypatch):
    _patch_cell(monkeypatch, error=RuntimeError("provider down"))

    assert await results_sufficient("q", []) is None


async def test_results_sufficient_fail_open_on_non_numeric(monkeypatch):
    _patch_cell(monkeypatch, text="looks good, no number though")

    assert await results_sufficient("q", []) is None


# ---------------------------------------------------------------------------
# K1: docs HyDE hardcode gate consults jev (BỎ — skip when sufficient)
# ---------------------------------------------------------------------------


def _stub_docs_db(monkeypatch, scores=(0.1, 0.1)):
    """Poor, thin results so the hardcoded HyDE trigger fires."""
    from wet import server

    db = MagicMock()
    db.get_library.return_value = {"id": "lib1", "discovery_version": 10**6}
    db.get_best_version.return_value = {"id": "ver1", "chunk_count": 3}
    db.search.return_value = [
        {"content": "c", "title": f"T{i}", "score": s} for i, s in enumerate(scores)
    ]
    monkeypatch.setattr(server, "_docs_db", db)
    return db


def _stub_embed(monkeypatch):
    from wet import embedder as embedder_mod

    class _FakeBackend:
        async def embed_single(self, text, dimensions=None):
            return [0.5] * 4

    monkeypatch.setattr(embedder_mod, "_backend", _FakeBackend())


def _stub_hyde(monkeypatch, return_value=None):
    return unittest.mock.patch(
        "wet.sources.search_strategies.generate_hyde_query",
        AsyncMock(return_value=return_value),
    )


async def _cached_index_payload(monkeypatch):
    from wet import server

    return await server._search_cached_index("fastapi", "routing", None, 10)


async def test_docs_hyde_skipped_when_jev_sufficient(monkeypatch):
    _stub_docs_db(monkeypatch)
    _stub_embed(monkeypatch)
    _patch_cell(monkeypatch, text="0.9")
    with _stub_hyde(monkeypatch) as hyde:
        out = await _cached_index_payload(monkeypatch)

    hyde.assert_not_awaited()  # BỎ: the strategy round never ran
    assert out["jev"] == {"gate": "hyde", "decision": "skip", "score": 0.9}
    assert out["results"][0]["score"] == 0.1


async def test_docs_hyde_runs_when_jev_insufficient(monkeypatch):
    _stub_docs_db(monkeypatch)
    _stub_embed(monkeypatch)
    _patch_cell(monkeypatch, text="0.2")
    with _stub_hyde(monkeypatch) as hyde:
        out = await _cached_index_payload(monkeypatch)

    hyde.assert_awaited_once()  # low score → proceed with the baseline gate
    assert out["jev"] == {"gate": "hyde", "decision": "proceed", "score": 0.2}


async def test_docs_hyde_fail_open_matches_baseline_exactly(monkeypatch):
    """Provider error ⇒ payload byte-identical to the jev-less baseline."""
    baselines = []
    for configured, error in ((True, RuntimeError("jev down")), (False, None)):
        _stub_docs_db(monkeypatch)
        _stub_embed(monkeypatch)
        _patch_cell(monkeypatch, configured=configured, error=error)
        with _stub_hyde(monkeypatch) as hyde:
            out = await _cached_index_payload(monkeypatch)
        hyde.assert_awaited_once()  # fail-open: HyDE ran as before
        assert "jev" not in out
        baselines.append(out)

    assert baselines[0] == baselines[1]


# ---------------------------------------------------------------------------
# N6: refine loop early stop (DỪNG — stop when sufficient)
# ---------------------------------------------------------------------------


def _chain_mock(responses):
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs["query"])
        chunk = responses[min(len(calls), len(responses)) - 1]
        return json.dumps(
            {"results": chunk, "total": len(chunk), "query": kwargs["query"]},
            ensure_ascii=False,
        )

    return fake, calls


async def _call_search(**overrides):
    from wet.server import search

    return await search(action="search", query="python tutorial", **overrides)


_WEAK = [{"url": "https://a/1", "title": "A", "snippet": "s", "score": 0.1}]
_HIT = [{"url": "https://b/1", "title": "B", "snippet": "s", "score": 0.9}]


async def test_refine_stops_early_when_jev_sufficient(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([_WEAK, _HIT])
    _patch_cell(monkeypatch, text="0.9")
    with (
        unittest.mock.patch("wet.sources.search_backends.run_search_chain", fake),
        unittest.mock.patch(
            "wet.sources.search_strategies.rewrite_query",
            AsyncMock(side_effect=["better python tutorial"]),
        ) as rewrite,
    ):
        out = payload(await _call_search(refine=True))

    rewrite.assert_not_awaited()  # DỪNG: the rewrite round never ran
    assert len(calls) == 1
    assert out["jev"] == {"gate": "refine", "decision": "stop", "score": 0.9}


async def test_refine_proceeds_with_receipt_when_jev_insufficient(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([_WEAK, _HIT])
    _patch_cell(monkeypatch, text="0.2")
    with (
        unittest.mock.patch("wet.sources.search_backends.run_search_chain", fake),
        unittest.mock.patch(
            "wet.sources.search_strategies.rewrite_query",
            AsyncMock(side_effect=["better python tutorial"]),
        ) as rewrite,
    ):
        out = payload(await _call_search(refine=True))

    rewrite.assert_awaited_once()  # low score → baseline loop continues
    assert len(calls) == 2
    assert out["jev"] == {"gate": "refine", "decision": "proceed", "score": 0.2}
    assert out["results"][0]["score"] == 0.9  # best round still wins


async def test_refine_fail_open_matches_baseline_exactly(monkeypatch):
    """Provider error ⇒ envelope identical to the jev-less refine baseline."""
    baselines = []
    for configured, error in ((True, RuntimeError("jev down")), (False, None)):
        monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
        fake, calls = _chain_mock([[], _HIT])
        _patch_cell(monkeypatch, configured=configured, error=error)
        with (
            unittest.mock.patch("wet.sources.search_backends.run_search_chain", fake),
            unittest.mock.patch(
                "wet.sources.search_strategies.rewrite_query",
                AsyncMock(side_effect=["better python tutorial"]),
            ) as rewrite,
        ):
            out = payload(await _call_search(refine=True))
        rewrite.assert_awaited_once()  # fail-open: rewrite round ran as before
        assert len(calls) == 2
        assert "jev" not in out
        baselines.append(out)

    assert baselines[0] == baselines[1]


async def test_refine_untouched_without_refine_flag(monkeypatch):
    """refine defaults off: no jev consultation, no receipt, one round."""
    monkeypatch.setenv("SEARCH_BACKENDS", "tavily")
    fake, calls = _chain_mock([_WEAK])
    _patch_cell(monkeypatch, text="0.9")
    with unittest.mock.patch("wet.sources.search_backends.run_search_chain", fake):
        out = payload(await _call_search())

    assert len(calls) == 1
    assert "jev" not in out


# ---------------------------------------------------------------------------
# K1 rerank-gate: skip the rerank backend when results already suffice (BỎ)
# ---------------------------------------------------------------------------


def _stub_reranker(monkeypatch):

    calls = []

    class _Reranker:
        def rerank(self, query, documents, top_n):
            calls.append((query, top_n))
            return [(i, 0.5) for i in range(min(top_n, len(documents)))]

    monkeypatch.setattr(
        "wet.reranker.resolve_rerank_backend_for_request", lambda: _Reranker()
    )
    return calls


async def test_rerank_gate_skips_backend_when_sufficient(monkeypatch):
    calls = _stub_reranker(monkeypatch)
    monkeypatch.setattr("wet.jev.results_sufficient", AsyncMock(return_value=0.9))
    from wet.server import _rerank_results

    results = [{"content": f"r{i}"} for i in range(5)]
    ranked, gate = await _rerank_results("q", results, top_n=3)

    assert calls == []  # BỎ: the rerank backend never ran
    assert ranked == results[:3]  # baseline order preserved
    assert gate == {"gate": "rerank", "decision": "skip", "score": 0.9}


async def test_rerank_gate_proceeds_when_insufficient(monkeypatch):
    calls = _stub_reranker(monkeypatch)
    monkeypatch.setattr("wet.jev.results_sufficient", AsyncMock(return_value=0.2))
    from wet.server import _rerank_results

    results = [{"content": f"r{i}"} for i in range(5)]
    ranked, gate = await _rerank_results("q", results, top_n=3)

    assert len(calls) == 1  # low score → baseline rerank as before
    assert gate == {"gate": "rerank", "decision": "rerank", "score": 0.2}
    assert ranked[0]["score"] == 0.5  # reranker output applied


async def test_rerank_gate_fail_open_matches_baseline_exactly(monkeypatch):
    """Unconfigured cell ⇒ output identical to the jev-less path."""
    from wet.server import _rerank_results

    results = [{"content": f"r{i}"} for i in range(5)]
    calls = _stub_reranker(monkeypatch)
    monkeypatch.setattr("wet.jev.results_sufficient", AsyncMock(return_value=None))
    ranked, gate = await _rerank_results("q", results, top_n=3)

    assert len(calls) == 1  # fail-open: rerank ran exactly as before
    assert gate is None
    assert ranked[0]["score"] == 0.5


async def test_docs_payload_merges_rerank_and_hyde_gates(monkeypatch):
    """Both K1 gates firing in one call ship a two-block receipt list."""
    # >= limit results so the rerank-gate consult runs at all (with fewer
    # candidates than top_n no rerank would happen, so no BỎ decision).
    _stub_docs_db(monkeypatch, scores=tuple(0.1 for _ in range(12)))
    _stub_embed(monkeypatch)
    _patch_cell(monkeypatch, text="0.9")
    _stub_reranker(monkeypatch)
    with _stub_hyde(monkeypatch) as hyde:
        out = await _cached_index_payload(monkeypatch)

    hyde.assert_not_awaited()
    assert out["jev"] == [
        {"gate": "rerank", "decision": "skip", "score": 0.9},
        {"gate": "hyde", "decision": "skip", "score": 0.9},
    ]
