"""Regression tests for Renovate's dependency update responsibilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "renovate.json"


def _load_config() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def test_library_ranges_and_lock_refreshes_have_separate_owners() -> None:
    config = _load_config()
    package_rules = config["packageRules"]

    assert config["rangeStrategy"] == "widen"
    assert config["lockFileMaintenance"]["enabled"] is True
    assert config["lockFileMaintenance"]["schedule"]
    assert all("rangeStrategy" not in rule for rule in package_rules)

    rules_by_slug = {
        rule["groupSlug"]: rule for rule in package_rules if "groupSlug" in rule
    }
    for group_slug in ("non-major-dev", "all-patch", "gha-digests"):
        assert rules_by_slug[group_slug]["minimumReleaseAge"] == "7 days"


def test_config_does_not_require_known_renovate_migrations() -> None:
    config = _load_config()
    package_rules = config["packageRules"]

    assert "golang" not in config
    # looked up by matcher instead of pinned as an exact dict, so adding a policy key
    # (e.g. minimumReleaseAge) to the rule does not force a test edit
    golang_rule = next(
        rule for rule in package_rules if rule.get("matchCategories") == ["golang"]
    )
    assert golang_rule["postUpdateOptions"] == ["gomodTidy"]
    assert all("matchPackagePatterns" not in rule for rule in package_rules)

    psr_rule = next(
        rule
        for rule in package_rules
        if rule.get("description") == "Pin PSR to v10 — block Renovate downgrades"
    )
    assert psr_rule["matchPackageNames"] == ["/^python-semantic-release//"]
