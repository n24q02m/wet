"""Tests for LLM integration over the [models.chat] provider cell (de-host seam).

The chat leg is one OpenAI-spec cell (base_url + api_key + model from
``~/.wet/config.toml``) served by the shared hull-core client. There are no
provider prefixes, no fallback chains, and no per-call api_base/api_key: the
``model`` / ``api_base`` / ``api_key`` / ``fallbacks`` arguments are accepted
for caller compatibility and ignored.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet.config import settings
from wet.llm import (
    acompletion,
    get_llm_config,
    has_llm_provider,
)


def _cell(model: str = "gemini-2.5-flash", configured: bool = True):
    return SimpleNamespace(
        task="chat",
        base_url="https://cell.example.com/v1",
        api_key="cell-key" if configured else "",
        model=model,
        configured=configured,
    )


@pytest.fixture
def chat_cell(monkeypatch):
    """A configured [models.chat] cell for the duration of the test."""
    monkeypatch.setattr("wet.runtime.model_cell", lambda task, settings=None: _cell())
    monkeypatch.setattr(
        "wet.runtime.cell_configured",
        lambda task, settings=None: task == "chat",
    )


@pytest.fixture
def no_chat_cell(monkeypatch):
    monkeypatch.setattr(
        "wet.runtime.model_cell",
        lambda task, settings=None: _cell(configured=False),
    )
    monkeypatch.setattr(
        "wet.runtime.cell_configured", lambda task, settings=None: False
    )


@pytest.fixture
def download_dir(tmp_path):
    """Point the media path-safety check at a tmp download dir, then restore."""
    original = settings.download_dir
    settings.download_dir = str(tmp_path)
    yield tmp_path
    settings.download_dir = original


# ---------------------------------------------------------------------------
# get_llm_config
# ---------------------------------------------------------------------------


def test_get_llm_config_from_cell(chat_cell):
    config = get_llm_config()
    assert config["model"] == "gemini-2.5-flash"
    assert config["api_base"] == "https://cell.example.com/v1"
    assert config["api_key"] == "cell-key"
    assert config["temperature"] is None
    assert config["fallbacks"] == []


def test_get_llm_config_unconfigured_cell(no_chat_cell):
    config = get_llm_config()
    assert config["model"] is None
    assert config["api_key"] == ""
    assert config["api_base"] is None
    assert config["temperature"] is None
    assert config["fallbacks"] == []


def test_get_llm_config_basic_structure(chat_cell):
    config = get_llm_config()
    assert {"model", "api_base", "api_key", "temperature", "fallbacks"} == set(config)


# ---------------------------------------------------------------------------
# provider availability gate
# ---------------------------------------------------------------------------


def test_has_llm_provider_true_when_cell_configured(chat_cell):
    assert has_llm_provider() is True


def test_has_llm_provider_false_when_cell_unconfigured(no_chat_cell):
    assert has_llm_provider() is False


# ---------------------------------------------------------------------------
# acompletion (chat cell via hull client)
# ---------------------------------------------------------------------------


def _chat_client(content: str = "ok"):
    client = MagicMock()
    client.chat = AsyncMock(return_value=content)
    return client


async def test_acompletion_returns_chat_result():
    with patch("wet.llm._chat_provider_client", return_value=_chat_client("hello")):
        result = await acompletion(messages=[{"role": "user", "content": "hi"}])

    assert result.choices[0].message.content == "hello"


async def test_acompletion_forwards_set_options_only():
    client = _chat_client("ok")
    with patch("wet.llm._chat_provider_client", return_value=client):
        await acompletion(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
            response_format={"type": "json_object"},
        )

    call_kwargs = client.chat.call_args[1]
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["response_format"] == {"type": "json_object"}

    client.chat.reset_mock()
    with patch("wet.llm._chat_provider_client", return_value=client):
        await acompletion(messages=[{"role": "user", "content": "hi"}])
    call_kwargs = client.chat.call_args[1]
    assert "temperature" not in call_kwargs
    assert "max_tokens" not in call_kwargs
    assert "response_format" not in call_kwargs


async def test_acompletion_ignores_legacy_caller_args():
    """model/api_base/api_key/fallbacks are accepted and ignored (cell-owned)."""
    client = _chat_client("ok")
    with patch("wet.llm._chat_provider_client", return_value=client):
        result = await acompletion(
            model="gemini/legacy-model",
            api_base="https://legacy.example.com/v1",
            api_key="legacy-key",
            fallbacks=["openai/fallback"],
            messages=[{"role": "user", "content": "hi"}],
        )

    assert result.choices[0].message.content == "ok"
    # Only the messages + set options reach the cell client.
    call_kwargs = client.chat.call_args[1]
    assert "model" not in call_kwargs
    assert "api_base" not in call_kwargs
    assert "api_key" not in call_kwargs
    assert "fallbacks" not in call_kwargs


async def test_acompletion_extra_kwargs_forwarded():
    client = _chat_client("ok")
    with patch("wet.llm._chat_provider_client", return_value=client):
        await acompletion(messages=[{"role": "user", "content": "hi"}], top_p=0.2)

    assert client.chat.call_args[1]["top_p"] == 0.2


def test_chat_client_built_once_from_cell(monkeypatch):
    """The chat-cell client is a process-lifetime singleton built lazily."""
    import wet.llm as llm_mod

    original = llm_mod._chat_client
    llm_mod._chat_client = None
    try:
        client = MagicMock()
        provider_client = MagicMock(return_value=client)
        monkeypatch.setattr("wet.runtime.provider_client", provider_client)

        first = llm_mod._chat_provider_client()
        second = llm_mod._chat_provider_client()

        assert first is client and second is client
        provider_client.assert_called_once_with("chat")
    finally:
        llm_mod._chat_client = original
