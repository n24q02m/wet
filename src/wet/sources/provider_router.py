"""Quality-first / cost-second provider router honoring WET_ROUTER_POLICY."""

from __future__ import annotations

import os
from collections.abc import Iterable

from wet import search_metrics
from wet.config import settings
from wet.sources.provider_registry import (
    ProviderCard,
    get_provider_card,
    is_circuit_open,
    list_provider_cards,
    serp_scrape_allowed,
)

VALID_POLICIES = ("free", "balanced", "quality")


def current_router_policy() -> str:
    """Resolve the active routing policy (default: ``free``)."""
    raw = (
        os.environ.get("WET_ROUTER_POLICY")
        or os.environ.get("ROUTER_POLICY")
        or getattr(settings, "router_policy", "free")
        or "free"
    )
    policy = raw.strip().lower()
    return policy if policy in VALID_POLICIES else "free"


def _tier_rank(card: ProviderCard, policy: str) -> tuple[int, int]:
    """Compute sorting key ``(tier_weight, card.priority)`` for ``policy``."""
    if policy == "quality":
        weights = {"byo_key": 0, "self_hosted": 1, "free": 2}
    elif policy == "balanced":
        weights = {"self_hosted": 0, "free": 1, "byo_key": 2}
    else:  # "free" (default keyless-first)
        weights = {"free": 0, "self_hosted": 1, "byo_key": 2}
    return (weights.get(card.cost_tier, 3), card.priority)


def select_provider_order(
    candidates: Iterable[str] | None = None,
    *,
    policy: str | None = None,
    required_capabilities: Iterable[str] = (),
) -> list[str]:
    """Order candidate providers by circuit health, budget, capability, and policy.

    Closed circuits come first, followed by capabilities match, then cost/quality
    rank under ``policy``. SERP scrapers are excluded unless
    ``WET_ALLOW_SERP_SCRAPE=true`` unless explicitly kept by the caller.
    """
    active_policy = policy if policy in VALID_POLICIES else current_router_policy()
    req_caps = frozenset(required_capabilities)
    allow_serp = serp_scrape_allowed()
    budget = getattr(settings, "wet_search_budget", 0) or 0

    names = (
        [n.strip().lower() for n in candidates if n.strip()]
        if candidates is not None
        else [c.name for c in list_provider_cards()]
    )

    eligible: list[tuple[tuple[int, int, int, int], str]] = []
    for name in names:
        card = get_provider_card(name)
        if card is None:
            eligible.append(((1, 1, 5, 100), name))
            continue
        if card.requires_serp_scrape and not allow_serp:
            continue
        if budget > 0 and search_metrics.query_count(name) >= budget:
            continue
        open_penalty = 1 if is_circuit_open(name) else 0
        cap_penalty = 0 if req_caps.issubset(card.capabilities) else 1
        t_weight, p_weight = _tier_rank(card, active_policy)
        eligible.append(((open_penalty, cap_penalty, t_weight, p_weight), name))

    eligible.sort(key=lambda item: item[0])
    return [name for _, name in eligible]
