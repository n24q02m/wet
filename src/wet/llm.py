"""LLM utilities for WET MCP Server — chat via the [models.chat] provider cell."""

from dataclasses import dataclass

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
        from wet.runtime import provider_client

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
    from wet.runtime import cell_configured

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
    from wet.runtime import model_cell

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
