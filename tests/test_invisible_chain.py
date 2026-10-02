"""Tests for the invisible chain branch in crawler._build_headless_strategies (fakes only)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from wet_mcp.sources.crawler import _build_headless_strategies, _resolve_identity


def _install_fake_hull_identity(
    monkeypatch: pytest.MonkeyPatch, built: dict[str, object]
) -> None:
    fp = types.ModuleType("hull_web.fingerprint")

    class FakeIdentity:
        seed = 7
        user_agent = "Mozilla/5.0 Firefox/147.0"

    def build_identity(*, seed):
        built["seed"] = seed
        return FakeIdentity()

    fp.build_identity = build_identity
    monkeypatch.setitem(sys.modules, "hull_web.fingerprint", fp)


def _install_fake_invisible(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(
            self,
            *,
            seed=0,
            profile_dir=None,
            humanize=True,
            headless=True,
            binary_path=None,
        ):
            captured["seed"] = seed
            captured["profile_dir"] = profile_dir
            captured["binary_path"] = binary_path

    class FakeStrategy:
        def __init__(self, timeout=60.0, provider=None):
            captured["timeout"] = timeout
            captured["provider"] = provider

    browsers = types.ModuleType("hull_web.browsers")
    browsers.BrowserlessClient = MagicMock(name="BrowserlessClient")
    invisible = types.ModuleType("hull_web.browsers.invisible")
    invisible.InvisibleProvider = FakeProvider
    strategies = types.ModuleType("hull_web.scraper.strategies")
    strategies.RemoteRenderStrategy = MagicMock(name="RemoteRenderStrategy")
    strategies.InvisibleStrategy = FakeStrategy
    monkeypatch.setitem(sys.modules, "hull_web.browsers", browsers)
    monkeypatch.setitem(sys.modules, "hull_web.browsers.invisible", invisible)
    monkeypatch.setitem(sys.modules, "hull_web.scraper.strategies", strategies)
    return captured


class TestResolveIdentity:
    def test_returns_profile_when_extra_installed(self, monkeypatch):
        built: dict[str, object] = {}
        _install_fake_hull_identity(monkeypatch, built)
        monkeypatch.setenv("WET_IDENTITY_SEED", "99")
        assert _resolve_identity().seed == 7
        assert built["seed"] == 99

    def test_returns_none_without_extra(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "hull_web.fingerprint", None)
        assert _resolve_identity() is None


class TestInvisibleBranch:
    def test_chain_with_invisible(self, monkeypatch, tmp_path):
        captured = _install_fake_invisible(monkeypatch)
        monkeypatch.setenv("BROWSER_BACKENDS", "native,browserless,invisible")
        monkeypatch.setenv("STEALTHFOX_BINARY", "/opt/stealthfox")
        monkeypatch.setattr(
            "wet_mcp.identity.identity_profile_dir", lambda: str(tmp_path / "profiles")
        )
        monkeypatch.setenv("WET_IDENTITY_SEED", "5")

        strats = _build_headless_strategies(stealth=True)

        assert set(strats) == {"headless", "browserless", "invisible"}
        assert captured["seed"] == 5
        assert captured["binary_path"] == "/opt/stealthfox"
        assert captured["profile_dir"] == str(tmp_path / "profiles")

    def test_invisible_only(self, monkeypatch, tmp_path):
        captured = _install_fake_invisible(monkeypatch)
        monkeypatch.setenv("BROWSER_BACKENDS", "invisible")
        monkeypatch.delenv("STEALTHFOX_BINARY", raising=False)
        monkeypatch.setattr(
            "wet_mcp.identity.identity_profile_dir", lambda: str(tmp_path / "profiles")
        )

        strats = _build_headless_strategies(stealth=True)

        assert set(strats) == {"invisible"}
        assert captured["binary_path"] is None


class TestIdentityPassThrough:
    def test_strategies_receive_identity(self, monkeypatch):
        built: dict[str, object] = {}
        _install_fake_hull_identity(monkeypatch, built)
        monkeypatch.setenv("BROWSER_BACKENDS", "native")
        monkeypatch.setenv("WET_IDENTITY_SEED", "3")

        strats = _build_headless_strategies(stealth=True, identity=_resolve_identity())

        assert strats["headless"].identity is not None

    def test_native_without_identity_keeps_none(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "hull_web.fingerprint", None)
        monkeypatch.setenv("BROWSER_BACKENDS", "native")

        strats = _build_headless_strategies(stealth=True, identity=None)

        assert strats["headless"].identity is None
