"""Tests for LLM integration over the [models.chat] provider cell (de-host seam).

The chat leg is one OpenAI-spec cell (base_url + api_key + model from
``~/.wet/config.toml``) served by the shared hull-core client. There are no
provider prefixes, no fallback chains, and no per-call api_base/api_key: the
``model`` / ``api_base`` / ``api_key`` / ``fallbacks`` arguments are accepted
for caller compatibility and ignored.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.config import settings
from wet_mcp.llm import (
    _AUDIO_INPUT_MODELS,
    _VISION_MODELS,
    _read_and_truncate,
    acompletion,
    analyze_media,
    encode_image,
    get_llm_config,
    get_model_capabilities,
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
    monkeypatch.setattr("wet_mcp.runtime.model_cell", lambda task, settings=None: _cell())
    monkeypatch.setattr(
        "wet_mcp.runtime.cell_configured",
        lambda task, settings=None: task == "chat",
    )


@pytest.fixture
def no_chat_cell(monkeypatch):
    monkeypatch.setattr(
        "wet_mcp.runtime.model_cell",
        lambda task, settings=None: _cell(configured=False),
    )
    monkeypatch.setattr(
        "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
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
    with patch("wet_mcp.llm._chat_provider_client", return_value=_chat_client("hello")):
        result = await acompletion(messages=[{"role": "user", "content": "hi"}])

    assert result.choices[0].message.content == "hello"


async def test_acompletion_forwards_set_options_only():
    client = _chat_client("ok")
    with patch("wet_mcp.llm._chat_provider_client", return_value=client):
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
    with patch("wet_mcp.llm._chat_provider_client", return_value=client):
        await acompletion(messages=[{"role": "user", "content": "hi"}])
    call_kwargs = client.chat.call_args[1]
    assert "temperature" not in call_kwargs
    assert "max_tokens" not in call_kwargs
    assert "response_format" not in call_kwargs


async def test_acompletion_ignores_legacy_caller_args():
    """model/api_base/api_key/fallbacks are accepted and ignored (cell-owned)."""
    client = _chat_client("ok")
    with patch("wet_mcp.llm._chat_provider_client", return_value=client):
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
    with patch("wet_mcp.llm._chat_provider_client", return_value=client):
        await acompletion(messages=[{"role": "user", "content": "hi"}], top_p=0.2)

    assert client.chat.call_args[1]["top_p"] == 0.2


def test_chat_client_built_once_from_cell(monkeypatch):
    """The chat-cell client is a process-lifetime singleton built lazily."""
    import wet_mcp.llm as llm_mod

    original = llm_mod._chat_client
    llm_mod._chat_client = None
    try:
        client = MagicMock()
        provider_client = MagicMock(return_value=client)
        monkeypatch.setattr("wet_mcp.runtime.provider_client", provider_client)

        first = llm_mod._chat_provider_client()
        second = llm_mod._chat_provider_client()

        assert first is client and second is client
        provider_client.assert_called_once_with("chat")
    finally:
        llm_mod._chat_client = original


# ---------------------------------------------------------------------------
# analyze_media
# ---------------------------------------------------------------------------


@patch("wet_mcp.llm.acompletion", new_callable=AsyncMock)
async def test_analyze_media_image(mock_completion, chat_cell, download_dir):
    img_path = download_dir / "test.jpg"
    img_path.write_bytes(b"fake-image-data")

    mock_completion.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="A nice cat."))])

    result = await analyze_media(str(img_path), "Describe")

    assert result == "A nice cat."
    mock_completion.assert_awaited_once()
    call_kwargs = mock_completion.call_args[1]
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"
    # "fake-image-data" base64 encoded is "ZmFrZS1pbWFnZS1kYXRh"
    assert "ZmFrZS1pbWFnZS1kYXRh" in str(call_kwargs["messages"][0]["content"])


async def test_analyze_media_no_cell(no_chat_cell, download_dir):
    img_path = download_dir / "test.jpg"
    img_path.touch()
    with patch.dict(os.environ, {}, clear=True):
        result = await analyze_media(str(img_path))

    assert "requires a configured [models.chat]" in result


async def test_analyze_media_file_not_found(chat_cell, download_dir):
    result = await analyze_media(str(download_dir / "non_existent_file.jpg"))
    assert "Error: File not found" in result


@patch("wet_mcp.llm.acompletion", new_callable=AsyncMock)
async def test_analyze_media_text_file(mock_completion, chat_cell, download_dir):
    txt_path = download_dir / "test.txt"
    txt_path.write_text("Hello")

    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Summary of text."))]
    )

    result = await analyze_media(str(txt_path))
    assert result == "Summary of text."

    mock_completion.assert_awaited_once()
    call_kwargs = mock_completion.call_args[1]
    assert "File Content:\n```\nHello\n```" in str(call_kwargs["messages"][0]["content"])


async def test_analyze_media_unsupported_type(chat_cell, download_dir):
    bin_path = download_dir / "test.bin"
    bin_path.write_bytes(b"\x00\x01")  # unknown binary

    result = await analyze_media(str(bin_path))
    assert "Unsupported media type" in result or "Cannot determine file type" in result


@patch("wet_mcp.llm.acompletion", new_callable=AsyncMock)
async def test_analyze_media_large_text_file(mock_completion, chat_cell, download_dir):
    txt_path = download_dir / "large.txt"
    txt_path.write_text("a" * 100005)

    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Summary of large text."))]
    )

    result = await analyze_media(str(txt_path))
    assert result == "Summary of large text."

    mock_completion.assert_awaited_once()
    sent_content = str(mock_completion.call_args[1]["messages"][0]["content"])
    assert "a" * 100000 + "\n...[truncated]" in sent_content
    assert "a" * 100001 not in sent_content


async def test_analyze_media_path_traversal(chat_cell, tmp_path):
    original = settings.download_dir
    settings.download_dir = str(tmp_path / "downloads")
    try:
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret data")

        result = await analyze_media(str(outside_file))
        assert "Error: Access denied" in result
        assert "download directory" in result
    finally:
        settings.download_dir = original


async def test_encode_image_valid(tmp_path):
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    result = await encode_image(str(img_path))
    import base64

    expected = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00").decode("utf-8")
    assert result == expected


async def test_encode_image_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        await encode_image(str(tmp_path / "nonexistent.png"))


async def test_encode_image_empty(tmp_path):
    img_path = tmp_path / "empty.png"
    img_path.write_bytes(b"")
    result = await encode_image(str(img_path))
    assert result == ""


async def test_read_and_truncate(tmp_path):
    txt_path = tmp_path / "small.txt"
    txt_path.write_text("hello", encoding="utf-8")
    assert await _read_and_truncate(str(txt_path)) == "hello"

    txt_path = tmp_path / "large.txt"
    large_content = "a" * 100005
    txt_path.write_text(large_content, encoding="utf-8")
    result = await _read_and_truncate(str(txt_path))
    assert len(result) == 100000 + len("\n...[truncated]")
    assert result.endswith("\n...[truncated]")


async def test_analyze_media_path_traversal_dotdot(chat_cell, tmp_path):
    original = settings.download_dir
    settings.download_dir = str(tmp_path / "downloads")
    try:
        (tmp_path / "downloads").mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret data")
        traversal_path = str((tmp_path / "downloads" / ".." / "secret.txt").resolve())

        result = await analyze_media(traversal_path)
        assert "Error: Access denied" in result
    finally:
        settings.download_dir = original


def test_analyze_media_tilde_download_dir(chat_cell, tmp_path, monkeypatch):
    """Tilde (~) in download_dir is expanded before the path-safety check."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows compat

    dl_dir = fake_home / ".wet-mcp" / "downloads"
    dl_dir.mkdir(parents=True)
    original = settings.download_dir
    settings.download_dir = "~/.wet-mcp/downloads"
    try:
        img_file = dl_dir / "test.jpg"
        img_file.write_bytes(b"fake-image-data")

        # Path check passes (no "Access denied"); the non-vision default cell
        # then refuses the image, which still proves the tilde was expanded.
        result = asyncio.run(analyze_media(str(img_file), "Describe"))
        assert "Access denied" not in result
    finally:
        settings.download_dir = original


# ---------------------------------------------------------------------------
# model capability maps (verbatim cell model ids, no provider prefixes)
# ---------------------------------------------------------------------------


def test_get_model_capabilities_comprehensive():
    for model in _VISION_MODELS:
        caps = get_model_capabilities(model)
        assert caps["vision"] is True, f"Model {model} should have vision"

    for model in _AUDIO_INPUT_MODELS:
        caps = get_model_capabilities(model)
        assert caps["audio_input"] is True, f"Model {model} should have audio input"


def test_get_model_capabilities_audio_output():
    with patch("wet_mcp.llm._AUDIO_OUTPUT_MODELS", {"test-audio-model"}):
        caps = get_model_capabilities("test-audio-model")
        assert caps["audio_output"] is True

        caps = get_model_capabilities("other-model")
        assert caps["audio_output"] is False


def test_get_model_capabilities_edge_cases():
    """Unknown / empty / whitespace model ids have no capabilities."""
    assert get_model_capabilities("provider/part1/part2")["vision"] is False

    caps = get_model_capabilities("")
    assert not any(caps.values())

    caps = get_model_capabilities("  gemini-2.5-flash  ")
    assert not any(caps.values())


def test_get_model_capabilities_known_models():
    """Vision + audio model vs vision-only model (bare cell model ids)."""
    caps = get_model_capabilities("gemini-3-flash-preview")
    assert caps == {
        "vision": True,
        "audio_input": True,
        "audio_output": False,
    }

    caps = get_model_capabilities("grok-4-1-fast-reasoning")
    assert caps == {
        "vision": True,
        "audio_input": False,
        "audio_output": False,
    }

    caps = get_model_capabilities("some-unknown-model")
    assert caps == {
        "vision": False,
        "audio_input": False,
        "audio_output": False,
    }
