"""Configuration and provider health handlers (WET-6, WET-17, WET-31)."""

from __future__ import annotations

from typing import Any

from wet.sources.provider_registry import registry_status_snapshot


def config_status_providers() -> dict[str, Any]:
    """Return provider metadata, SERP opt-in state, policy, and breaker status."""
    return registry_status_snapshot()
