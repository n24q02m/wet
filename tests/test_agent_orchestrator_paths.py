"""Edge paths of ``extract(action="agent")``.

Boundaries mocked: the search chain (``run_search_chain``), the page fetch
(``crawler.extract``) and the chat cell's provider client. Everything between
them (prompt building, payload validation, synthesis call shape) is real.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet.sources import agent_orchestrator as ao


@pytest.fixture
def _llm_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_prompt_without_extracts_forbids_invention():
    """With nothing extracted the prompt tells the model to say so."""
    prompt = ao.build_cited_prompt("what is x", [], token_budget=1000)

    assert "No sources could be extracted" in prompt
    assert "'what is x'" in prompt


async def test_extract_many_reports_unusable_payloads():
    """A fetch returning non-JSON or an empty list becomes a per-URL error
    entry, in input order, instead of failing the whole agent run."""
    fetch = AsyncMock(side_effect=["<html>not json</html>", "[]"])

    with patch("wet.sources.crawler.extract", fetch):
        out = await ao._extract_many(["https://a.com", "https://b.com"])

    assert out == [
        {"url": "https://a.com", "error": "extract returned non-JSON payload"},
        {"url": "https://b.com", "error": "extract returned empty payload"},
    ]


async def test_llm_synthesize_sends_the_prompt_to_the_chat_cell():
    """The synthesis call sends the cited prompt as one user message and
    returns the cell's text."""
    client = MagicMock()
    client.chat = AsyncMock(return_value="answer [1]")

    with (
        patch("wet.llm._chat_provider_client", return_value=client),
        patch(
            "wet.llm.get_llm_config",
            return_value={"model": "cell-model", "temperature": None},
        ),
    ):
        text = await ao._llm_synthesize("PROMPT", model_override=None)

    assert text == "answer [1]"
    assert client.chat.await_args is not None
    messages = client.chat.await_args.args[0]
    assert messages == [{"role": "user", "content": "PROMPT"}]


async def test_search_payload_that_is_not_an_object_fails_the_run(_llm_key):
    """A JSON array from the search chain is a hard failure, named by type."""
    with patch.object(
        ao, "run_search_chain", AsyncMock(return_value=json.dumps(["x"]))
    ):
        out = await ao.run_agent("q")

    assert out == "Error: search failed: ValueError"


async def test_search_results_that_are_not_a_list_fail_the_run(_llm_key):
    """``results`` must be a list; anything else is reported, not iterated."""
    with patch.object(
        ao, "run_search_chain", AsyncMock(return_value=json.dumps({"results": "x"}))
    ):
        out = await ao.run_agent("q")

    assert out == "Error: search failed: results is not a list"
