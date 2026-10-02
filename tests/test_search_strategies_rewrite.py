"""``rewrite_query`` — the N6 refine-loop rewrite step (search_strategies).

Real contract: returns exactly one usable rewritten query, or ``None``
when refinement cannot proceed (no provider, useless answer, a repeat of
the original or an already-tried query). The provider boundary is a
recorded fake — no network.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from wet_mcp.sources.search_strategies import rewrite_query


def _llm(content: str | None):
    """An acompletion response-shaped object: .choices[0].message.content."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@contextmanager
def _provider(content: str | None = None, *, error=None, capture: list | None = None):
    async def fake_acompletion(**kwargs):
        if capture is not None:
            capture.append(kwargs)
        if error is not None:
            raise error
        return _llm(content)

    with (
        patch("wet_mcp.sources.search_strategies.has_llm_provider", return_value=True),
        patch(
            "wet_mcp.sources.search_strategies.get_llm_config",
            return_value={"model": "gpt-x", "fallbacks": None, "temperature": 0},
        ),
        patch(
            "wet_mcp.sources.search_strategies.acompletion",
            side_effect=fake_acompletion,
        ),
    ):
        yield


async def test_rewrite_returns_cleaned_single_line_query():
    with _provider('  "fastapi async testing"  '):
        assert await rewrite_query("fastapi test") == "fastapi async testing"


async def test_rewrite_takes_only_the_first_line():
    with _provider("line one\nline two"):
        assert await rewrite_query("q") == "line one"


async def test_rewrite_prompt_carries_query_reason_and_avoid_list():
    captured: list = []
    with _provider("better query terms", capture=captured):
        out = await rewrite_query(
            "python async",
            avoid=["python async io", "asyncio guide"],
            reason="results were all tutorials",
        )

    assert out == "better query terms"
    prompt = captured[0]["messages"][0]["content"]
    assert "python async" in prompt
    assert "results were all tutorials" in prompt
    assert "python async io; asyncio guide" in prompt
    # Token bound for a one-line answer.
    assert captured[0]["max_tokens"] == 60


async def test_rewrite_none_without_provider():
    with patch(
        "wet_mcp.sources.search_strategies.has_llm_provider", return_value=False
    ):
        assert await rewrite_query("q", avoid=["x"]) is None


async def test_rewrite_rejects_useless_answers():
    for content in ("", "   ", None, "q"):  # empty, blank, absent, verbatim repeat
        with _provider(content):
            assert await rewrite_query("q") is None


async def test_rewrite_case_insensitive_repeat_is_rejected():
    with _provider("Python Async"):
        assert await rewrite_query("python async") is None


async def test_rewrite_rejects_already_tried_query():
    with _provider("tried one"):
        assert await rewrite_query("q", avoid=["tried one"]) is None


async def test_rewrite_provider_failure_returns_none():
    with _provider(error=RuntimeError("provider down")):
        assert await rewrite_query("q") is None
