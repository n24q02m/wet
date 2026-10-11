from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import run_contract

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeKey:
    """Scripted ``/api/v1/key`` readings: each read pops the next value."""

    def __init__(self, usages: list[float], limit_remaining: float | None = None):
        self.usages = list(usages)
        self.limit_remaining = limit_remaining
        self.reads = 0

    async def __call__(self) -> run_contract.KeyUsage:
        self.reads += 1
        usage = self.usages.pop(0) if len(self.usages) > 1 else self.usages[0]
        return run_contract.KeyUsage(
            usage_usd=usage, limit_remaining_usd=self.limit_remaining
        )


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _guard(key: _FakeKey, *, cap: float = 5.0, clock=None) -> run_contract.SpendGuard:
    return run_contract.SpendGuard(
        cap_usd=cap,
        read_usage=key,
        clock=clock or _Clock(),
        log=lambda _line: None,
    )


async def test_start_refuses_when_key_remaining_is_below_cap():
    # Account credit can be plentiful while the key's own monthly limit is
    # nearly exhausted; the run would then die mid-suite with the money spent.
    guard = _guard(_FakeKey([10.0], limit_remaining=1.99))

    with pytest.raises(run_contract.SpendCapExceeded, match="1.99"):
        await guard.start()


async def test_start_accepts_an_unlimited_key():
    guard = _guard(_FakeKey([10.0], limit_remaining=None))

    await guard.start()

    assert guard.spent_usd == 0.0


async def test_check_measures_spend_against_this_runs_baseline_not_key_totals():
    # The key already carries 7.74 USD from earlier runs today; only the delta
    # since this run started counts against this run's cap.
    key = _FakeKey([7.74, 8.10])
    guard = _guard(key)
    await guard.start()

    await guard.check("web_search", done=1, total=500, force=True)

    assert guard.spent_usd == pytest.approx(0.36)


async def test_check_aborts_once_this_run_reaches_the_cap():
    guard = _guard(_FakeKey([2.0, 7.0]))
    await guard.start()

    with pytest.raises(run_contract.SpendCapExceeded, match="5.00"):
        await guard.check("web_search", done=300, total=500, force=True)


async def test_check_aborts_early_when_the_projection_exceeds_the_cap():
    # 50 web cases cost 1.00 USD -> 500 would cost ~10 USD: stop at 1 USD spent
    # instead of burning the whole cap and leaving no usable artifact.
    guard = _guard(_FakeKey([0.0, 1.0]))
    await guard.start()

    with pytest.raises(run_contract.SpendCapExceeded, match="projected"):
        await guard.check("web_search", done=50, total=500, force=True)


async def test_projection_waits_for_enough_samples():
    guard = _guard(_FakeKey([0.0, 0.5]))
    await guard.start()

    # 5 cases at 0.10 USD each would project 50 USD, but 5 is too few samples.
    await guard.check("web_search", done=5, total=500, force=True)

    assert guard.spent_usd == pytest.approx(0.5)


async def test_projection_is_per_suite():
    # Spend accrued during extract must not be divided by web-case counts.
    key = _FakeKey([0.0, 0.40, 0.40, 0.60])
    guard = _guard(key)
    await guard.start()
    await guard.check("extract", done=200, total=200, force=True)
    await guard.check("web_search", done=0, total=500, force=True)

    # 0.20 USD over 100 web cases -> 1.00 USD for the suite, well under cap.
    await guard.check("web_search", done=100, total=500, force=True)

    assert guard.spent_usd == pytest.approx(0.60)


async def test_check_is_throttled_unless_forced():
    clock = _Clock()
    key = _FakeKey([0.0, 0.1, 0.2])
    guard = _guard(key, clock=clock)
    await guard.start()

    await guard.check("web_search", done=1, total=500)
    reads_after_first = key.reads
    clock.now += 1.0
    await guard.check("web_search", done=2, total=500)
    assert key.reads == reads_after_first

    clock.now += run_contract.SPEND_CHECK_INTERVAL_S
    await guard.check("web_search", done=3, total=500)
    assert key.reads == reads_after_first + 1


async def test_check_logs_progress_lines():
    lines: list[str] = []
    guard = run_contract.SpendGuard(
        cap_usd=5.0,
        read_usage=_FakeKey([1.0, 1.5]),
        clock=_Clock(),
        log=lines.append,
    )
    await guard.start()

    await guard.check("web_search", done=40, total=50, force=True)

    assert any("web_search 40/50" in line and "0.50/5.00" in line for line in lines)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 5.0), ("", 5.0), ("  ", 5.0), ("3.5", 3.5)],
)
def test_spend_cap_defaults_to_the_workflow_default(raw, expected):
    assert run_contract.spend_cap_from_env(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "nan", "inf"])
def test_spend_cap_rejects_non_positive_or_garbage(raw):
    with pytest.raises(run_contract.contract.ContractError):
        run_contract.spend_cap_from_env(raw)


async def test_bounded_runner_preserves_case_order_and_concurrency():
    active = 0
    peak = 0

    async def runner(case: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01 * (5 - case % 5))
        active -= 1
        return case * 10

    seen: list[int] = []

    async def on_done(done: int) -> None:
        seen.append(done)

    results = await run_contract.run_cases_bounded(
        list(range(12)), runner, concurrency=3, on_done=on_done
    )

    assert results == [case * 10 for case in range(12)]
    assert peak == 3
    assert sorted(seen) == list(range(1, 13))


async def test_bounded_runner_stops_scheduling_after_a_spend_abort():
    started: list[int] = []

    async def runner(case: int) -> int:
        started.append(case)
        await asyncio.sleep(0)
        return case

    async def on_done(done: int) -> None:
        if done == 2:
            raise run_contract.SpendCapExceeded("cap reached")

    with pytest.raises(run_contract.SpendCapExceeded, match="cap reached"):
        await run_contract.run_cases_bounded(
            list(range(50)), runner, concurrency=2, on_done=on_done
        )

    assert len(started) < 50


def test_web_concurrency_applies_only_to_llm_mediated_backends():
    # Directly-measured backends keep their p95 gate, so they stay serial.
    assert run_contract.web_concurrency_for("openrouter") > 1
    assert run_contract.web_concurrency_for("searxng") == 1


def test_benchmark_workflow_passes_the_cap_to_the_run_step():
    benchmark = (REPO_ROOT / ".github/workflows/benchmark.yml").read_text(
        encoding="utf-8"
    )
    run_step = benchmark[benchmark.index("name: Execute live MCP benchmark") :]
    run_step = run_step[: run_step.index("- name:", 1)]

    assert "OPENROUTER_SPEND_CAP_USD: ${{ vars.OPENROUTER_SPEND_CAP_USD }}" in run_step
