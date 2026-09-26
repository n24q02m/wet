"""LLM utilities for WET MCP Server — chat via the [models.chat] provider cell."""

import asyncio
import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from wet_mcp.config import settings

# ---------------------------------------------------------------------------
# Capability maps (vision / audio support detection)
# ---------------------------------------------------------------------------

_VISION_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
}

_AUDIO_INPUT_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
}

_AUDIO_OUTPUT_MODELS: set[str] = set()


# ---------------------------------------------------------------------------
# Chat cell client (single per-task cell, cached for the process lifetime)
# ---------------------------------------------------------------------------

# Process-shared OpenAI-spec client for the [models.chat] cell. One cell, one
# client: base_url, api_key, and model come from the cell and never per call.
_chat_client = None


def _chat_provider_client():
    """Return the cached chat-cell client (built lazily on first use)."""
    global _chat_client
    if _chat_client is None:
        from wet_mcp.runtime import provider_client

        _chat_client = provider_client("chat")
    return _chat_client


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class ChatResult:
    """Minimal OpenAI-shaped completion result.

    The chat cell returns plain assistant text; this wrapper keeps the
    ``response.choices[0].message.content`` access pattern every existing
    caller uses.
    """

    choices: list[_Choice]

    def __init__(self, content: str) -> None:
        self.choices = [_Choice(_Message(content))]


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------


def has_llm_provider() -> bool:
    """Whether the [models.chat] cell is configured (base_url + key + model)."""
    from wet_mcp.runtime import cell_configured

    return cell_configured("chat")


# Back-compat alias (internal callers).
_has_llm_provider = has_llm_provider


# ---------------------------------------------------------------------------
# Async completion (chat cell)
# ---------------------------------------------------------------------------


async def acompletion(
    *,
    model: str | None = None,
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    fallbacks: list[str] | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> ChatResult:
    """Run one chat completion via the [models.chat] provider cell.

    The cell owns base_url, api_key, and model: the ``model``, ``api_base``
    and ``api_key`` arguments are accepted for caller compatibility and
    IGNORED -- the cell's model is verbatim, there are no provider prefixes.
    ``fallbacks`` is likewise accepted and ignored: a single per-task cell has
    no fallback chain, and its presence never fails the call.
    """
    client = _chat_provider_client()

    options = {
        key: value
        for key, value in (
            ("temperature", temperature),
            ("max_tokens", max_tokens),
            ("response_format", response_format),
            *kwargs.items(),
        )
        if value is not None
    }
    content = await client.chat(messages, **options)
    return ChatResult(content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_llm_config() -> dict:
    """Describe the [models.chat] cell for feature-gating and call sites.

    ``model`` is ``None`` (and ``api_key`` empty) when the cell is
    unconfigured -- callers treat a falsy model as feature-off. There is no
    chain any more, so ``fallbacks`` is always empty, and temperature is left
    to the provider default (the cell has no temperature field).
    """
    from wet_mcp.runtime import model_cell

    cell = model_cell("chat")
    if not cell.configured:
        return {
            "model": None,
            "api_base": None,
            "api_key": "",
            "temperature": None,
            "fallbacks": [],
        }
    return {
        "model": cell.model,
        "api_base": cell.base_url,
        "api_key": cell.api_key,
        "temperature": None,
        "fallbacks": [],
    }


def get_model_capabilities(model: str) -> dict:
    """Check model's media capabilities against the static maps.

    The de-hosted stack has no provider registry to consult, so vision/audio
    support is the hardcoded map only; the cell's model id is verbatim.

    Returns:
        Dict with 'vision', 'audio_input', 'audio_output' booleans.
    """
    return {
        "vision": model in _VISION_MODELS,
        "audio_input": model in _AUDIO_INPUT_MODELS,
        "audio_output": model in _AUDIO_OUTPUT_MODELS,
    }


async def encode_image(image_path: str) -> str:
    """Encode image to base64.

    Offload blocking I/O to thread pool to prevent event loop lag.
    """
    data = await asyncio.to_thread(Path(image_path).read_bytes)
    return base64.b64encode(data).decode("utf-8")


async def _read_and_truncate(path: str) -> str:
    """Read file and truncate if too long.

    Uses asyncio.to_thread for non-blocking file I/O.
    """

    def _read():
        with open(path, encoding="utf-8") as f:
            return f.read(100001)

    text = await asyncio.to_thread(_read)
    if len(text) > 100000:
        text = text[:100000] + "\n...[truncated]"
    return text


async def analyze_media(
    media_path: str, prompt: str = "Describe this media in detail."
) -> str:
    """Analyze media file using the configured chat cell with auto-capability detection."""
    if not has_llm_provider():
        return (
            "Error: LLM analysis requires a configured [models.chat] provider "
            "cell (base_url + api_key + model in ~/.wet/config.toml)."
        )

    path_obj = Path(media_path).resolve()
    download_dir = Path(settings.download_dir).expanduser().resolve()
    if not path_obj.is_relative_to(download_dir):
        return f"Error: Access denied — file must be within download directory ({download_dir})"
    if not path_obj.exists():
        return f"Error: File not found at {media_path}"

    # Determine mime type
    mime_type, _ = mimetypes.guess_type(media_path)
    if not mime_type:
        return f"Error: Cannot determine file type for {media_path}"
    config = get_llm_config()

    # Handle text files directly
    if mime_type.startswith("text/") or mime_type in [
        "application/json",
        "application/javascript",
        "application/xml",
    ]:
        try:
            content = await _read_and_truncate(media_path)
            logger.info(f"Analyzing text file with model: {config['model']}")

            messages = [
                {
                    "role": "user",
                    "content": f"{prompt}\n\nFile Content:\n```\n{content}\n```",
                }
            ]
            response = await acompletion(messages=messages)
            return str(response.choices[0].message.content)
        except Exception as e:
            return f"Error analyzing text file: {e}"

    # Check model capabilities for media
    caps = get_model_capabilities(config["model"])

    # Validate capability vs file type
    if mime_type.startswith("image/"):
        if not caps["vision"]:
            return f"Error: Model {config['model']} does not support vision/images."
    elif mime_type.startswith("audio/"):
        if not caps["audio_input"]:
            return f"Error: Model {config['model']} does not support audio input."
    elif mime_type.startswith("video/"):
        if not caps["vision"]:
            return f"Error: Model {config['model']} does not support video (requires vision)."
    else:
        return f"Error: Unsupported media type: {mime_type}"

    try:
        logger.info(f"Analyzing media with model: {config['model']}")

        base64_image = await encode_image(media_path)
        data_url = f"data:{mime_type};base64,{base64_image}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        response = await acompletion(messages=messages)

        return str(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return f"Error analyzing media: {str(e)}"
