"""Tests for the E1-f identity seed + E1-e invisible chain wiring (fakes only)."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from wet.identity import get_or_create_identity_seed, identity_profile_dir


@pytest.fixture()
def isolated_sub_root(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Point sub_root at a tmp dir so persistence never touches ~/.wet."""
    root = tmp_path / "sub"
    root.mkdir(parents=True)
    monkeypatch.setattr("wet.runtime.sub_root", lambda namespace=None: root)
    monkeypatch.delenv("WET_IDENTITY_SEED", raising=False)
    monkeypatch.setattr("wet.config.settings.identity_seed", 0)
    return root


class TestIdentitySeed:
    def test_env_pin_wins(self, monkeypatch, isolated_sub_root):
        monkeypatch.setenv("WET_IDENTITY_SEED", "4242")
        assert get_or_create_identity_seed() == 4242

    def test_settings_seed_wins_over_file(self, monkeypatch, isolated_sub_root):
        (isolated_sub_root / "identity.json").write_text(
            '{"identity_seed": 111}', encoding="utf-8"
        )
        monkeypatch.setattr("wet.config.settings.identity_seed", 222)
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

    def test_configured_profile_dir_wins(self, monkeypatch, isolated_sub_root):
        """An explicit IDENTITY_PROFILE_DIR is used as-is."""
        monkeypatch.setattr("wet.config.settings.identity_profile_dir", "/p/prof")
        assert identity_profile_dir() == "/p/prof"

    def test_corrupted_file_derives_and_rewrites_a_seed(self, isolated_sub_root):
        """An unreadable identity file must not wedge startup: a fresh seed is
        derived and persisted over the corrupted one."""
        path = isolated_sub_root / "identity.json"
        path.write_text("{not json", encoding="utf-8")

        seed = get_or_create_identity_seed()

        assert seed > 0
        assert json.loads(path.read_text(encoding="utf-8")) == {"identity_seed": seed}

    @pytest.mark.parametrize("stored", ['{"identity_seed": 0}', '["x"]'])
    def test_unusable_persisted_seed_is_replaced(self, isolated_sub_root, stored):
        """A non-positive seed, or a file that is not an object, is ignored."""
        path = isolated_sub_root / "identity.json"
        path.write_text(stored, encoding="utf-8")

        seed = get_or_create_identity_seed()

        assert seed > 0
        assert json.loads(path.read_text(encoding="utf-8")) == {"identity_seed": seed}

    def test_unwritable_namespace_keeps_an_in_memory_seed(self, monkeypatch, tmp_path):
        """When the seed cannot be persisted the server still gets one."""
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("", encoding="utf-8")
        monkeypatch.setattr("wet.runtime.sub_root", lambda namespace=None: blocker)
        monkeypatch.delenv("WET_IDENTITY_SEED", raising=False)
        monkeypatch.setattr("wet.config.settings.identity_seed", 0)

        assert get_or_create_identity_seed() > 0
        assert blocker.read_text(encoding="utf-8") == ""


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
        from wet.sources._browser_sessions import SessionPool

        calls: list[str] = []
        _stub_open_interact(monkeypatch, calls)

        subs = iter(["alice", "alice", "bob"])
        monkeypatch.setattr("wet.runtime.current_sub", lambda: next(subs))

        pool = SessionPool()
        ops_a1 = await pool.get("s1", "https://example.com")
        ops_a2 = await pool.get("s1", "https://example.com")  # same sub -> reused
        ops_b = await pool.get("s1", "https://example.com")  # other sub -> new

        assert ops_a1 is ops_a2
        assert ops_b is not ops_a1
        assert len(calls) == 2  # one fresh session per sub
