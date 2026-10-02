"""In-memory per-provider search metrics: latency EMA + query counters.

Process-local by design -- no persistence, no new tool. Exposed read-only
through the existing ``config`` tool ``status`` payload. The EMA (alpha 0.3)
smooths single-call spikes while staying responsive to provider regressions;
query counters back the optional per-provider budget (``WET_SEARCH_BUDGET``).
"""

from __future__ import annotations

# EMA weight of the newest sample.
_EMA_ALPHA = 0.3

_latency_ema: dict[str, float] = {}
_query_counts: dict[str, int] = {}


def record_query(provider: str) -> None:
    """Count one query attempt against ``provider`` (budget accounting)."""
    _query_counts[provider] = _query_counts.get(provider, 0) + 1


def query_count(provider: str) -> int:
    """Queries attempted so far against ``provider`` this process."""
    return _query_counts.get(provider, 0)


def record_latency(provider: str, seconds: float) -> None:
    """Fold one latency sample into the provider's exponential moving average."""
    prev = _latency_ema.get(provider)
    if prev is None:
        _latency_ema[provider] = seconds
    else:
        _latency_ema[provider] = _EMA_ALPHA * seconds + (1 - _EMA_ALPHA) * prev


def latency_ema(provider: str) -> float | None:
    """Current latency EMA for ``provider``, or ``None`` before any call."""
    return _latency_ema.get(provider)


def snapshot() -> dict:
    """Status-payload view: ``latency_ema_seconds`` + ``query_counts``."""
    return {
        "latency_ema_seconds": {k: round(v, 4) for k, v in _latency_ema.items()},
        "query_counts": dict(_query_counts),
    }
