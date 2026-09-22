"""Tests for the SyncBackend abstract base class."""

from __future__ import annotations

from pathlib import Path

import pytest

from wet_mcp.sync.base import SyncBackend


def test_sync_backend_is_abstract() -> None:
    """SyncBackend should not be instantiable due to abstract methods."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class SyncBackend"):
        SyncBackend()  # ty: ignore[call-non-callable] — intentional: asserts the abstract TypeError


class MockBackend(SyncBackend):
    """Concrete implementation of SyncBackend for testing."""

    name = "mock"

    async def push(self, db_path: Path) -> bool:
        return True

    async def pull(self, db_path: Path) -> Path | None:
        return db_path

    async def health_check(self) -> bool:
        return True

    @property
    def supports_oauth_setup(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_mock_backend_contract() -> None:
    """Verify a concrete subclass satisfies the SyncBackend contract."""
    backend = MockBackend()
    assert backend.name == "mock"
    assert await backend.push(Path("test.db")) is True
    assert await backend.pull(Path("test.db")) == Path("test.db")
    assert await backend.health_check() is True
    assert backend.supports_oauth_setup is False


def test_default_name() -> None:
    """Verify the default name is an empty string."""

    class PartialBackend(SyncBackend):
        async def push(self, db_path: Path) -> bool:
            return True

        async def pull(self, db_path: Path) -> Path | None:
            return None

        async def health_check(self) -> bool:
            return True

        @property
        def supports_oauth_setup(self) -> bool:
            return False

    assert PartialBackend().name == ""
