"""Tests for the E1-f identity seed + E1-e invisible chain wiring (fakes only)."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from wet_mcp.identity import get_or_create_identity_seed, identity_profile_dir


@pytest.fixture()
def isolated_sub_root(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Point sub_root at a tmp dir so persistence never touches ~/.wet."""
    root = tmp_path / "sub"
    root.mkdir(parents=True)
    monkeypatch.setattr("wet_mcp.runtime.sub_root", lambda namespace=None: root)
    monkeypatch.delenv("WET_IDENTITY_SEED", raising=False)
    monkeypatch.setattr("wet_mcp.config.settings.identity_seed", 0)
    return root


class TestIdentitySeed:
    def test_env_pin_wins(self, monkeypatch, isolated_sub_root):
        monkeypatch.setenv("WET_IDENTITY_SEED", "4242")
        assert get_or_create_identity_seed() == 4242

    def test_settings_seed_wins_over_file(self, monkeypatch, isolated_sub_root):
        (isolated_sub_root / "identity.json").write_text(
            '{"identity_seed": 111}', encoding="utf-8"
        )
        monkeypatch.setattr("wet_mcp.config.settings.identity_seed", 222)
        assert get_or_create_identity_seed() == 222

    def test_persists_and_reloads(self, isolated_sub_root):
        first = get_or_create_identity_seed()
        assert first > 0
        assert (isolated_sub_root / "identity.json").exists()
        assert get_or_create_identity_seed() == first

    def test_invalid_env_falls_through(self, monkeypatch, isolated_sub_root):
        monkeypatch.setenv("WET_IDENTITY_SEED", "not-a-number")
        seed = get_or_create_identity_seed()
        assert seed > 0

    def test_profile_dir_default_under_sub(self, isolated_sub_root):
        assert identity_profile_dir() == str(isolated_sub_root / "profiles")


class _FakeEntryOps:
    pass


def _stub_open_interact(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Stub the pool's hull_web session opener (no browser)."""

    async def fake(url, headless=True, timeout_ms=30000):
        calls.append(url)
        pw = MagicMock()
        pw.stop = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        page = MagicMock()
        return pw, browser, page, _FakeEntryOps()

    stub = types.ModuleType("hull_web.browsers.interact")
    stub.open_interact_session = fake
    stub.InteractOps = object
    monkeypatch.setitem(sys.modules, "hull_web.browsers.interact", stub)


class TestPoolSubKeying:
    async def test_same_session_id_isolated_per_sub(self, monkeypatch):
        from wet_mcp.sources._browser_sessions import SessionPool

        calls: list[str] = []
        _stub_open_interact(monkeypatch, calls)

        subs = iter(["alice", "alice", "bob"])
        monkeypatch.setattr("wet_mcp.runtime.current_sub", lambda: next(subs))

        pool = SessionPool()
        ops_a1 = await pool.get("s1", "https://example.com")
        ops_a2 = await pool.get("s1", "https://example.com")  # same sub -> reused
        ops_b = await pool.get("s1", "https://example.com")  # other sub -> new

        assert ops_a1 is ops_a2
        assert ops_b is not ops_a1
        assert len(calls) == 2  # one fresh session per sub
