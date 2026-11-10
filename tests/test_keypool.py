"""Provider key pools: hull's rotation, wired through wet's provider surfaces.

wet resolves provider credentials in two places -- the per-task model cells
(``wet.runtime.provider_client``) and the cloud search backends -- and both now
read hull's credential pool instead of a single key. These tests pin the
product contract of that adoption:

* a 429 cools the key down by ``Retry-After`` and the next key serves;
* a 401 disables the key and the next key serves;
* an exhausted pool raises a redacted ``ProviderUnavailable`` naming the
  provider and the cooldown, never a key;
* the legacy single-key config still works and is migrated once (idempotent);
* a named account selects its own pool;
* concurrent calls never receive the same leased credential.
"""

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable

import httpx
import pytest
from hull_core.config.models import ModelCell
from hull_core.credentials import AccountRegistry

from wet import keypool
from wet.keypool import (
    PooledProviderClient,
    ProviderConfigError,
    ProviderUnavailable,
    migrate_legacy_key,
    pool_for_task,
    reset_credential_state,
)

PROVIDER = "openrouter"
BASE_URL = "https://openrouter.ai/api/v1"
CHAT_BODY = {"choices": [{"message": {"content": "ok"}}]}


@pytest.fixture(autouse=True)
def _fresh_pool(tmp_path, monkeypatch):
    """Isolated credential store + no legacy keys leaking in from the host."""
    monkeypatch.setenv(keypool.POOL_DB_ENV, str(tmp_path / "hull.db"))
    for name in (
        "HULL_CHAT_API_KEY",
        "HULL_EMBED_API_KEY",
        "HULL_RERANK_API_KEY",
        "HULL_JEV_SCORE_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_credential_state()
    yield
    reset_credential_state()


def _cell(api_key: str = "", *, task: str = "chat", account: str = "") -> ModelCell:
    return ModelCell(
        task=task,
        base_url=BASE_URL,
        api_key=api_key,
        model="z-ai/glm-5.3-flash",
        provider=PROVIDER,
        account=account,
    )


# 200 = a chat completion, (status, headers) = a rejected request, or a gate
# coroutine the concurrency test holds open.
Outcome = int | tuple[int, dict[str, str]] | Callable[..., Awaitable[httpx.Response]]


def _handler(seen: list[str], outcomes: dict[str, Outcome]):
    """Fake provider: records the bearer key, then answers per key."""

    async def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].removeprefix("Bearer ")
        seen.append(key)
        outcome = outcomes.get(key, 200)
        if isinstance(outcome, tuple):
            status, headers = outcome
            return httpx.Response(status, headers=headers, text=f"rejected key {key}")
        if isinstance(outcome, int):
            return httpx.Response(200, json=CHAT_BODY)
        return await outcome(request, key)

    return handler


def _client(seen: list[str], outcomes: dict[str, Outcome]) -> PooledProviderClient:
    return PooledProviderClient(
        _cell(),
        auth_mode="no-auth",
        timeout=5.0,
        transport=httpx.MockTransport(_handler(seen, outcomes)),
    )


async def _chat(client: PooledProviderClient) -> str:
    return await client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


async def test_429_cools_the_key_down_by_retry_after_and_the_next_serves():
    store = keypool.credential_store()
    cooled = store.add_credential(PROVIDER, "sk-first-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-second-0002", base_url=BASE_URL)
    seen: list[str] = []
    client = _client(seen, {"sk-first-0001": (429, {"retry-after": "7"})})

    assert await _chat(client) == "ok"

    assert seen == ["sk-first-0001", "sk-second-0002"]
    health = {row.id: row for row in store.pool_health(PROVIDER)}
    assert health[cooled.id].last_status == 429
    assert health[cooled.id].disabled is False
    # The provider's own hint, not hull's 60 s default.
    assert 1.0 < health[cooled.id].cooldown_remaining <= 7.0
    assert health[cooled.id].usable is False


async def test_401_disables_the_key_and_the_next_one_serves():
    store = keypool.credential_store()
    revoked = store.add_credential(PROVIDER, "sk-revoked-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-good-0002", base_url=BASE_URL)
    seen: list[str] = []
    client = _client(seen, {"sk-revoked-0001": (401, {})})

    assert await _chat(client) == "ok"

    assert seen == ["sk-revoked-0001", "sk-good-0002"]
    health = {row.id: row for row in store.pool_health(PROVIDER)}
    assert health[revoked.id].disabled is True
    assert health[revoked.id].last_status == 401


async def test_exhaustion_names_the_provider_and_cooldown_but_no_key():
    store = keypool.credential_store()
    store.add_credential(PROVIDER, "sk-alpha-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-beta-0002", base_url=BASE_URL)
    seen: list[str] = []
    client = _client(
        seen,
        {
            "sk-alpha-0001": (429, {"retry-after": "45"}),
            "sk-beta-0002": (429, {"retry-after": "45"}),
        },
    )

    with pytest.raises(ProviderUnavailable) as caught:
        await _chat(client)

    error = caught.value
    assert error.provider == PROVIDER
    assert error.retry_after is not None
    assert 1.0 < error.retry_after <= 45.0
    message = f"{error}"
    assert "'openrouter'" in message
    assert "retry in" in message
    assert "cooling_down=2" in message
    # The provider echoed the key back in its 429 body; hull redacts every
    # stored key before it reaches wet's error.
    assert "sk-" not in message
    assert "sk-" not in (error.last_error or "")


async def test_rate_limit_reset_header_also_cools_the_key_down():
    store = keypool.credential_store()
    cooled = store.add_credential(PROVIDER, "sk-first-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-second-0002", base_url=BASE_URL)
    reset_at = str(int(time.time()) + 30)
    client = _client([], {"sk-first-0001": (429, {"x-ratelimit-reset": reset_at})})

    assert await _chat(client) == "ok"

    health = {row.id: row for row in store.pool_health(PROVIDER)}
    assert 1.0 < health[cooled.id].cooldown_remaining <= 30.0


async def test_other_statuses_do_not_touch_credential_health():
    store = keypool.credential_store()
    store.add_credential(PROVIDER, "sk-first-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-second-0002", base_url=BASE_URL)
    client = _client([], {"sk-first-0001": (400, {})})

    with pytest.raises(Exception) as caught:
        await _chat(client)

    assert "400" in str(caught.value)
    assert all(row.failure_count == 0 for row in store.pool_health(PROVIDER))


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def test_named_account_reads_its_own_pool():
    store = keypool.credential_store()
    account = AccountRegistry(store).add(provider=PROVIDER, name="Work")
    store.add_credential(
        PROVIDER, "sk-work-0001", base_url=BASE_URL, account_id=account.account_id
    )
    store.add_credential(PROVIDER, "sk-default-0001", base_url=BASE_URL)

    pool = pool_for_task(_cell(account=account.account_id))

    assert [credential.api_key for credential in pool.credentials()] == ["sk-work-0001"]
    assert pool_for_task(_cell()).credentials()[0].api_key == "sk-default-0001"


def test_unregistered_account_is_a_config_error():
    with pytest.raises(ProviderConfigError, match="not registered"):
        pool_for_task(_cell(account="openrouter:missing"))


def test_account_of_another_provider_is_a_config_error():
    store = keypool.credential_store()
    AccountRegistry(store).add(provider="openai", name="Elsewhere")

    with pytest.raises(ProviderConfigError, match="belongs to provider"):
        pool_for_task(_cell(account="openai:elsewhere"))


# ---------------------------------------------------------------------------
# Legacy single-key config
# ---------------------------------------------------------------------------


async def test_legacy_single_key_cell_still_serves_and_is_migrated(monkeypatch):
    monkeypatch.setenv("HULL_CHAT_API_KEY", "sk-legacy-0001")
    cell = _cell("sk-legacy-0001")
    seen: list[str] = []

    client = PooledProviderClient(
        cell, timeout=5.0, transport=httpx.MockTransport(_handler(seen, {}))
    )

    assert await _chat(client) == "ok"
    assert seen == ["sk-legacy-0001"]
    assert [item.api_key for item in pool_for_task(cell).credentials()] == [
        "sk-legacy-0001"
    ]
    # The env var is the operator's material: migrated, never removed.
    assert os.environ["HULL_CHAT_API_KEY"] == "sk-legacy-0001"


def test_migration_is_idempotent():
    cell = _cell("sk-legacy-0001")

    first = migrate_legacy_key(cell)
    second = migrate_legacy_key(cell)

    assert first is not None and second is not None
    assert (first.added, first.skipped) == (1, 0)
    assert (second.added, second.skipped) == (0, 1)
    assert len(pool_for_task(cell).credentials()) == 1


def test_keyless_cell_with_a_seeded_pool_counts_as_configured(monkeypatch):
    from wet.runtime import cell_configured, reset_settings_cache

    reset_settings_cache()
    monkeypatch.setattr(
        "wet.runtime.model_cell", lambda task, settings=None: _cell("", task=task)
    )
    assert cell_configured("chat") is False

    keypool.credential_store().add_credential(
        PROVIDER, "sk-seeded-0001", base_url=BASE_URL
    )

    assert cell_configured("chat") is True


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


async def test_concurrent_calls_never_share_a_leased_credential():
    store = keypool.credential_store()
    store.add_credential(PROVIDER, "sk-alpha-0001", base_url=BASE_URL)
    store.add_credential(PROVIDER, "sk-beta-0002", base_url=BASE_URL)

    in_flight = 0
    both_leased = asyncio.Event()
    release = asyncio.Event()

    async def gate(request: httpx.Request, key: str) -> httpx.Response:
        nonlocal in_flight
        in_flight += 1
        if in_flight >= 2:
            both_leased.set()
        await release.wait()
        in_flight -= 1
        return httpx.Response(200, json=CHAT_BODY)

    seen: list[str] = []
    client = PooledProviderClient(
        _cell(),
        timeout=10.0,
        transport=httpx.MockTransport(
            _handler(seen, {"sk-alpha-0001": gate, "sk-beta-0002": gate})
        ),
    )

    running = [asyncio.create_task(_chat(client)) for _ in range(2)]
    await asyncio.wait_for(both_leased.wait(), timeout=5)

    with pytest.raises(ProviderUnavailable) as caught:
        await _chat(client)

    assert "leased=2" in str(caught.value)
    release.set()
    assert await asyncio.gather(*running) == ["ok", "ok"]
    assert sorted(seen) == ["sk-alpha-0001", "sk-beta-0002"]


# ---------------------------------------------------------------------------
# Cloud search backends go through the same pool
# ---------------------------------------------------------------------------


async def test_search_backend_rotates_through_the_pool():
    from wet.sources.search_backends import TavilyBackend

    used: list[str] = []

    async def fake_post(self, url, **kwargs):
        key = kwargs["json"]["api_key"]
        used.append(key)
        if key == "bad":
            return httpx.Response(429, headers={"retry-after": "12"}, text="slow down")
        return httpx.Response(200, json={"results": []})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx.AsyncClient, "post", fake_post)
        out = await TavilyBackend(["bad", "good"]).search("q")

    assert "results" in json.loads(out)
    assert used == ["bad", "good"]
    health = keypool.credential_store().pool_health("tavily")
    assert [row.last_status for row in health] == [429, 200]
    assert 1.0 < health[0].cooldown_remaining <= 12.0


async def test_search_backend_keyless_path_is_unchanged():
    from wet.sources.search_backends import FirecrawlBackend

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"data": {"search": []}})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx.AsyncClient, "post", fake_post)
        out = await FirecrawlBackend([]).search("q")

    assert json.loads(out)["total"] == 0


async def test_a_single_credential_serves_concurrent_embedding_batches():
    """One key, wet's 8-way embed fan-out: shared, not spurious exhaustion."""
    store = keypool.credential_store()
    store.add_credential(PROVIDER, "sk-solo-0001", base_url=BASE_URL)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        body = json.loads(request.content)
        data = [
            {"index": index, "embedding": [0.5, 0.5]}
            for index, _ in enumerate(body["input"])
        ]
        return httpx.Response(200, json={"data": data})

    client = PooledProviderClient(
        _cell(task="embed"),
        timeout=5.0,
        transport=httpx.MockTransport(handler),
        store=store,
    )

    results = await asyncio.gather(*[client.embeddings(["x"]) for _ in range(8)])

    assert len(results) == 8
    assert calls == 8
    assert all(row.failure_count == 0 for row in store.pool_health(PROVIDER))


# ---------------------------------------------------------------------------
# runtime.provider_client is the adoption point the task cells use
# ---------------------------------------------------------------------------


def _write_config(body: str) -> None:
    from wet import runtime

    config_dir = runtime.wet_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(body, encoding="utf-8")
    runtime.reset_settings_cache()


async def test_runtime_provider_client_seeds_and_serves_the_cell_key():
    from wet import runtime

    _write_config('[models.chat]\napi_key = "sk-legacy-0001"\n')
    try:
        client = runtime.provider_client("chat")

        assert isinstance(client, PooledProviderClient)
        assert client.cell.task == "chat"
        assert [item.api_key for item in client.pool.credentials()] == [
            "sk-legacy-0001"
        ]
        # One pooled client per cell identity, so its per-credential HTTP
        # clients and rotation memo survive across tool calls.
        assert runtime.provider_client("chat") is client
        assert runtime.cell_configured("chat") is True
    finally:
        runtime.reset_settings_cache()


async def test_runtime_provider_client_reads_a_keyless_cells_seeded_pool():
    from wet import runtime

    _write_config('[models.chat]\nmodel = "z-ai/glm-5.3-flash"\n')
    keypool.credential_store().add_credential(
        PROVIDER, "sk-seeded-0001", base_url=BASE_URL
    )
    try:
        client = runtime.provider_client("chat")

        assert [item.api_key for item in client.pool.credentials()] == [
            "sk-seeded-0001"
        ]
        assert runtime.cell_configured("chat") is True
    finally:
        runtime.reset_settings_cache()
