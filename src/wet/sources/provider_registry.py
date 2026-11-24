"""Search provider metadata cards and in-process circuit-breaker registry."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from wet import search_metrics
from wet.config import settings


@dataclass(frozen=True, slots=True)
class ProviderCard:
    """Declarative capability and cost metadata for a search backend."""

    name: str
    cost_tier: str  # "free" | "self_hosted" | "byo_key"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    requires_key: bool = False
    key_env: str = ""
    requires_serp_scrape: bool = False
    priority: int = 50
    description: str = ""


PROVIDER_REGISTRY: dict[str, ProviderCard] = {
    "keenable": ProviderCard(
        name="keenable",
        cost_tier="free",
        capabilities=frozenset({"search", "web"}),
        requires_key=False,
        key_env="KEENABLE_API_KEY",
        priority=25,
        description="Keyless-capable web search public endpoint.",
    ),
    "firecrawl": ProviderCard(
        name="firecrawl",
        cost_tier="free",
        capabilities=frozenset({"search", "web", "extract"}),
        requires_key=False,
        key_env="FIRECRAWL_API_KEY",
        priority=30,
        description="Firecrawl search (keyless fallback or BYO key).",
    ),
    "searxng": ProviderCard(
        name="searxng",
        cost_tier="self_hosted",
        capabilities=frozenset(
            {"search", "web", "region", "academic", "recency", "domains"}
        ),
        requires_key=False,
        key_env="SEARXNG_URL",
        priority=20,
        description="Self-hosted SearXNG metasearch (requires SEARXNG_URL).",
    ),
    "tavily": ProviderCard(
        name="tavily",
        cost_tier="byo_key",
        capabilities=frozenset(
            {"search", "web", "region", "recency", "domains", "academic"}
        ),
        requires_key=True,
        key_env="TAVILY_API_KEY",
        priority=10,
        description="Tavily AI search API (BYO key).",
    ),
    "brave": ProviderCard(
        name="brave",
        cost_tier="byo_key",
        capabilities=frozenset({"search", "web", "region", "recency"}),
        requires_key=True,
        key_env="BRAVE_API_KEY",
        priority=15,
        description="Brave Search API (BYO key).",
    ),
    "exa": ProviderCard(
        name="exa",
        cost_tier="byo_key",
        capabilities=frozenset(
            {"search", "web", "semantic", "domains", "recency", "academic"}
        ),
        requires_key=True,
        key_env="EXA_API_KEY",
        priority=12,
        description="Exa neural search API (BYO key).",
    ),
    "kagi": ProviderCard(
        name="kagi",
        cost_tier="byo_key",
        capabilities=frozenset({"search", "web"}),
        requires_key=True,
        key_env="KAGI_API_KEY",
        priority=18,
        description="Kagi Search API (BYO key).",
    ),
    "openrouter": ProviderCard(
        name="openrouter",
        cost_tier="byo_key",
        capabilities=frozenset({"search", "web", "synthesis"}),
        requires_key=True,
        key_env="OPENROUTER_API_KEY",
        priority=40,
        description="OpenRouter online web-plugin search (BYO key + OPENROUTER_MODEL).",
    ),
    "duckduckgo": ProviderCard(
        name="duckduckgo",
        cost_tier="free",
        capabilities=frozenset({"search", "web", "recency"}),
        requires_key=False,
        requires_serp_scrape=True,
        priority=80,
        description="DuckDuckGo HTML SERP scraper (disabled unless WET_ALLOW_SERP_SCRAPE=true).",
    ),
    "startpage": ProviderCard(
        name="startpage",
        cost_tier="free",
        capabilities=frozenset({"search", "web", "recency"}),
        requires_key=False,
        requires_serp_scrape=True,
        priority=85,
        description="Startpage HTML SERP scraper (disabled unless WET_ALLOW_SERP_SCRAPE=true).",
    ),
}

# In-process circuit breaker state per provider.
_FAILURE_THRESHOLD = 3
_OPEN_COOLDOWN_SECONDS = 120.0
_breaker_failures: dict[str, int] = {}
_breaker_open_until: dict[str, float] = {}


def serp_scrape_allowed() -> bool:
    """Return True iff HTML SERP scraping is explicitly enabled."""
    raw = os.environ.get("WET_ALLOW_SERP_SCRAPE") or os.environ.get("ALLOW_SERP_SCRAPE")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(getattr(settings, "allow_serp_scrape", False))


def record_provider_success(provider: str) -> None:
    """Reset consecutive failure count and close any half-open circuit."""
    _breaker_failures.pop(provider, None)
    _breaker_open_until.pop(provider, None)


def record_provider_failure(
    provider: str, *, cooldown: float = _OPEN_COOLDOWN_SECONDS
) -> None:
    """Increment failure counter and open circuit after threshold failures."""
    count = _breaker_failures.get(provider, 0) + 1
    _breaker_failures[provider] = count
    if count >= _FAILURE_THRESHOLD:
        _breaker_open_until[provider] = time.monotonic() + cooldown


def is_circuit_open(provider: str) -> bool:
    """Return True if the provider circuit breaker is currently open."""
    until = _breaker_open_until.get(provider)
    if until is None:
        return False
    if time.monotonic() >= until:
        _breaker_open_until.pop(provider, None)
        _breaker_failures[provider] = max(0, _FAILURE_THRESHOLD - 1)
        return False
    return True


def reset_breakers() -> None:
    """Clear all circuit-breaker state (primarily for tests)."""
    _breaker_failures.clear()
    _breaker_open_until.clear()


def get_provider_card(name: str) -> ProviderCard | None:
    """Return the ProviderCard for ``name``, case-insensitive."""
    return PROVIDER_REGISTRY.get(name.strip().lower())


def list_provider_cards() -> list[ProviderCard]:
    """Return all registered providers sorted by default priority."""
    return sorted(PROVIDER_REGISTRY.values(), key=lambda c: c.priority)


def registry_status_snapshot() -> dict[str, object]:
    """Summarize registered provider configuration and health for ``config status``."""
    metrics = search_metrics.snapshot()
    budget = getattr(settings, "wet_search_budget", 0) or 0
    providers_out: dict[str, dict[str, object]] = {}
    for card in list_provider_cards():
        open_circuit = is_circuit_open(card.name)
        q_count = int(metrics.get("query_counts", {}).get(card.name, 0))
        budget_ok = budget <= 0 or q_count < budget
        providers_out[card.name] = {
            "cost_tier": card.cost_tier,
            "requires_key": card.requires_key,
            "requires_serp_scrape": card.requires_serp_scrape,
            "enabled": (not card.requires_serp_scrape) or serp_scrape_allowed(),
            "circuit_open": open_circuit,
            "budget_ok": budget_ok,
            "query_count": q_count,
            "capabilities": sorted(card.capabilities),
        }
    return {
        "allow_serp_scrape": serp_scrape_allowed(),
        "router_policy": (
            os.environ.get("WET_ROUTER_POLICY")
            or getattr(settings, "router_policy", "free")
        ).lower(),
        "providers": providers_out,
    }
