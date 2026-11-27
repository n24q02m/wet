"""Steering running research jobs (``job_op="steer"``).

Search, extraction and synthesis are patched with in-memory fakes, so these
tests make no network call and no paid LLM call. Jobs are held at a known
orchestration step with ``asyncio.Event`` gates instead of timing sleeps.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wet.db import DocsDB
from wet.handlers.extract_handlers import handle_async_agent
from wet.sources import agent_orchestrator as ao
from wet.sources.agent_jobs import (
    _JOB_TASKS,
    get_research_job,
    resume_research_job,
    start_research_job,
    steer_research_job,
)
from wet.sources.agent_orchestrator import (
    ResearchDirection,
    apply_steering,
    is_excluded,
    validate_steering,
)


def _search_payload(urls: list[str]) -> str:
    return json.dumps(
        {"results": [{"url": u, "title": f"T {u}", "source": "fake"} for u in urls]}
    )


class FakeResearch:
    """In-memory search/extract/synthesis with optional gates per step."""

    def __init__(self, rounds: dict[str, list[str]]) -> None:
        self.rounds = rounds
        self.searches: list[tuple[str, int]] = []
        self.extracted: list[list[str]] = []
        self.prompts: list[str] = []
        self.search_gate: asyncio.Event | None = None
        self.synth_gate: asyncio.Event | None = None
        self.in_search = asyncio.Event()
        self.in_synth = asyncio.Event()

    async def search(self, query: str, max_results: int = 10) -> str:
        self.searches.append((query, max_results))
        self.in_search.set()
        if self.search_gate is not None:
            await self.search_gate.wait()
        return _search_payload(self.rounds.get(query, []))

    async def extract(self, urls: list[str]) -> list[dict]:
        self.extracted.append(list(urls))
        return [{"url": u, "markdown": f"body of {u}"} for u in urls]

    async def synthesize(self, prompt: str, model: str | None) -> str:
        self.prompts.append(prompt)
        self.in_synth.set()
        if self.synth_gate is not None:
            await self.synth_gate.wait()
        return "answer [1]"

    def patches(self):
        return (
            patch.object(ao, "run_search_chain", side_effect=self.search),
            patch.object(ao, "_extract_many", side_effect=self.extract),
            patch.object(ao, "_llm_synthesize", side_effect=self.synthesize),
            patch.object(ao, "detect_llm_provider", return_value="TEST"),
        )


async def _run(fake: FakeResearch, on_step=None, **kwargs):
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        return await ao.run_agent("q", max_urls=2, on_step=on_step, **kwargs)


# ---------------------------------------------------------------------------
# validate_steering / apply_steering
# ---------------------------------------------------------------------------


def test_validate_rejects_non_dict_and_empty_changes():
    assert validate_steering(None)[1] is not None
    assert validate_steering(["add_focus"])[1] is not None
    changes, error = validate_steering({})
    assert changes is None
    assert error is not None
    assert "at least one" in error


def test_validate_rejects_unknown_keys():
    _, error = validate_steering({"focus": ["x"]})
    assert error is not None
    assert "focus" in error
    assert "add_focus" in error


def test_validate_normalises_lists_and_hosts():
    changes, error = validate_steering(
        {
            "add_focus": "  pricing ",
            "remove_focus": ["Old", "old", ""],
            "add_constraints": ["only 2025 sources"],
            "exclude_sources": ["https://www.Reddit.com/r/x", "medium.com/@a", "  "],
            "depth": 3,
        }
    )
    assert error is None
    assert changes == {
        "add_focus": ["pricing"],
        "remove_focus": ["Old"],
        "add_constraints": ["only 2025 sources"],
        "exclude_sources": ["reddit.com", "medium.com"],
        "depth": 3,
    }


@pytest.mark.parametrize(
    "changes,needle",
    [
        ({"depth": True}, "depth"),
        ({"depth": -1}, "depth"),
        ({"depth": 6}, "depth"),
        ({"depth": "2"}, "depth"),
        ({"add_focus": [1]}, "add_focus"),
        ({"add_focus": 5}, "add_focus"),
        ({"add_focus": ["x" * 201]}, "200"),
        ({"add_constraints": [f"c{i}" for i in range(21)]}, "20"),
        ({"exclude_sources": ["not a host!"]}, "exclude_sources"),
        ({"exclude_sources": ["http://[broken"]}, "exclude_sources"),
        ({"add_focus": ["   "]}, "at least one"),
    ],
)
def test_validate_rejects_bad_values(changes, needle):
    result, error = validate_steering(changes)
    assert result is None
    assert error is not None
    assert needle in error


def test_apply_steering_updates_direction_without_mutating_input():
    base = ResearchDirection(focus=["a"], remaining_depth=2)
    out = apply_steering(
        base,
        {
            "add_focus": ["b", "A"],
            "remove_focus": ["a"],
            "add_constraints": ["peer reviewed"],
            "exclude_sources": ["bad.example"],
            "depth": 0,
        },
    )
    assert out.focus == ["b"]
    assert out.constraints == ["peer reviewed"]
    assert out.exclude_sources == ["bad.example"]
    assert out.remaining_depth == 0
    assert base.focus == ["a"]
    assert base.remaining_depth == 2


def test_apply_steering_dedupes_repeated_changes():
    once = apply_steering(
        ResearchDirection(), {"add_constraints": ["x"], "exclude_sources": ["a.b"]}
    )
    twice = apply_steering(once, {"add_constraints": ["X"], "exclude_sources": ["a.b"]})
    assert twice.constraints == ["x"]
    assert twice.exclude_sources == ["a.b"]


@pytest.mark.parametrize(
    "url,excluded",
    [
        ("https://bad.example/a", True),
        ("https://www.bad.example/a", True),
        ("https://sub.bad.example/a", True),
        ("https://notbad.example/a", False),
        ("https://good.example/a", False),
        ("not a url", False),
        ("http://[broken/a", False),
    ],
)
def test_is_excluded_matches_host_and_subdomains(url, excluded):
    assert is_excluded(url, ["bad.example"]) is excluded


def test_direction_round_trips_through_dict():
    d = ResearchDirection(
        focus=["a"], constraints=["b"], exclude_sources=["c.d"], remaining_depth=1
    )
    assert ResearchDirection.from_dict(d.to_dict()) == d
    assert ResearchDirection.from_dict(None) == ResearchDirection()
    assert ResearchDirection.from_dict({"remaining_depth": "x"}) == ResearchDirection()


# ---------------------------------------------------------------------------
# run_agent checkpoints
# ---------------------------------------------------------------------------


async def test_run_agent_without_steering_runs_one_round():
    fake = FakeResearch({"q": ["https://a.example/1", "https://b.example/2"]})
    result = await _run(fake)
    assert fake.searches == [("q", 2)]
    assert fake.extracted == [["https://a.example/1", "https://b.example/2"]]
    assert [s["url"] for s in result["sources"]] == [
        "https://a.example/1",
        "https://b.example/2",
    ]
    assert "Focus" not in fake.prompts[0]


async def test_steer_is_applied_at_the_next_step():
    fake = FakeResearch(
        {
            "q": ["https://good.example/1", "https://bad.example/2"],
            "q pricing": [
                "https://good.example/1",
                "https://bad.example/4",
                "https://new.example/3",
            ],
        }
    )
    steps: list[tuple[str, int]] = []

    async def on_step(step, round_no, direction):
        steps.append((step, round_no))
        if (step, round_no) == ("extract", 1):
            return apply_steering(
                direction,
                {
                    "exclude_sources": ["bad.example"],
                    "add_focus": ["pricing"],
                    "add_constraints": ["cite prices in USD"],
                },
            )
        return direction

    result = await _run(fake, on_step=on_step)

    assert steps == [
        ("search", 1),
        ("extract", 1),
        ("search", 2),
        ("extract", 2),
        ("synthesize", 2),
    ]
    # Round 1 dropped the excluded host before extraction; round 2 searched
    # the new focus topic and skipped already-seen and excluded URLs.
    assert fake.extracted == [["https://good.example/1"], ["https://new.example/3"]]
    assert [q for q, _ in fake.searches] == ["q", "q pricing"]
    assert [s["url"] for s in result["sources"]] == [
        "https://good.example/1",
        "https://new.example/3",
    ]
    assert [s["index"] for s in result["sources"]] == [1, 2]
    assert "pricing" in fake.prompts[0]
    assert "cite prices in USD" in fake.prompts[0]


async def test_depth_zero_stops_follow_up_rounds():
    fake = FakeResearch({"q": ["https://a.example/1"]})

    async def on_step(step, round_no, direction):
        if step == "extract":
            return apply_steering(direction, {"add_focus": ["more"], "depth": 0})
        return direction

    result = await _run(fake, on_step=on_step)
    assert [q for q, _ in fake.searches] == ["q"]
    assert "more" in fake.prompts[0]
    assert result["sources"][0]["url"] == "https://a.example/1"


async def test_follow_up_rounds_are_bounded_by_remaining_depth():
    fake = FakeResearch({"q": ["https://a.example/1"]})

    async def on_step(step, round_no, direction):
        if (step, round_no) == ("extract", 1):
            return apply_steering(direction, {"add_focus": ["x", "y", "z"], "depth": 2})
        return direction

    await _run(fake, on_step=on_step)
    assert [q for q, _ in fake.searches] == ["q", "q x", "q y"]


async def test_steer_at_synthesis_checkpoint_loops_back_to_search():
    fake = FakeResearch(
        {"q": ["https://a.example/1"], "q late": ["https://b.example/2"]}
    )
    steps: list[tuple[str, int]] = []

    async def on_step(step, round_no, direction):
        steps.append((step, round_no))
        if (step, round_no) == ("synthesize", 1):
            return apply_steering(direction, {"add_focus": ["late"]})
        return direction

    result = await _run(fake, on_step=on_step)
    assert steps == [
        ("search", 1),
        ("extract", 1),
        ("synthesize", 1),
        ("search", 2),
        ("extract", 2),
        ("synthesize", 2),
    ]
    assert len(result["sources"]) == 2


async def test_exclusion_after_extraction_drops_sources_from_synthesis():
    fake = FakeResearch({"q": ["https://a.example/1", "https://b.example/2"]})

    async def on_step(step, round_no, direction):
        if step == "synthesize":
            return apply_steering(direction, {"exclude_sources": ["b.example"]})
        return direction

    result = await _run(fake, on_step=on_step)
    assert [s["url"] for s in result["sources"]] == ["https://a.example/1"]
    assert "b.example" not in fake.prompts[0]


async def test_excluding_every_source_returns_no_results_without_llm():
    fake = FakeResearch({"q": ["https://a.example/1"]})

    async def on_step(step, round_no, direction):
        if step == "synthesize":
            return apply_steering(direction, {"exclude_sources": ["a.example"]})
        return direction

    result = await _run(fake, on_step=on_step)
    assert result["sources"] == []
    assert fake.prompts == []


async def test_initial_direction_shapes_first_round():
    fake = FakeResearch({"q": ["https://bad.example/1", "https://ok.example/2"]})
    direction = ResearchDirection(exclude_sources=["bad.example"])
    result = await _run(fake, direction=direction)
    assert fake.searches == [("q", 3)]  # over-fetch to cover the exclusion
    assert [s["url"] for s in result["sources"]] == ["https://ok.example/2"]


async def test_follow_up_search_error_keeps_earlier_rounds():
    fake = FakeResearch({"q": ["https://a.example/1"]})

    async def broken_search(query, max_results=10):
        if query != "q":
            raise RuntimeError("provider down")
        return _search_payload(["https://a.example/1"])

    async def on_step(step, round_no, direction):
        if (step, round_no) == ("extract", 1):
            return apply_steering(direction, {"add_focus": ["x"]})
        return direction

    p1, p2, p3, p4 = fake.patches()
    with (
        p1,
        p2,
        p3,
        p4,
        patch.object(ao, "run_search_chain", side_effect=broken_search),
    ):
        result = await ao.run_agent("q", max_urls=2, on_step=on_step)
    assert isinstance(result, dict)
    assert [s["url"] for s in result["sources"]] == ["https://a.example/1"]


async def test_follow_up_round_respects_total_url_cap():
    many = [f"https://h{i}.example/" for i in range(40)]
    fake = FakeResearch({"q": many[:20], "q more": many[20:]})

    async def on_step(step, round_no, direction):
        if (step, round_no) == ("extract", 1):
            return apply_steering(direction, {"add_focus": ["more"]})
        return direction

    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        await ao.run_agent("q", max_urls=20, on_step=on_step)
    assert sum(len(batch) for batch in fake.extracted) == ao._HARD_MAX_URLS
    assert [q for q, _ in fake.searches] == ["q"]


def test_build_cited_prompt_includes_direction_only_when_set():
    extracts = [{"url": "https://a.example/", "markdown": "x"}]
    plain = ao.build_cited_prompt("q", extracts, 1000)
    assert plain == ao.build_cited_prompt("q", extracts, 1000, ResearchDirection())
    steered = ao.build_cited_prompt(
        "q",
        extracts,
        1000,
        ResearchDirection(focus=["pricing"], constraints=["USD only"]),
    )
    assert "pricing" in steered
    assert "USD only" in steered
    assert "pricing" not in plain


# ---------------------------------------------------------------------------
# Job lifecycle: steer_research_job + status
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path):
    database = DocsDB(tmp_path / "jobs.db", embedding_dims=0)
    yield database
    for task in list(_JOB_TASKS.values()):
        task.cancel()
    _JOB_TASKS.clear()
    database.close()


async def _wait_status(db, job_id, wanted, timeout=5.0):
    async def _poll():
        while get_research_job(db, job_id=job_id)["status"] not in wanted:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)
    return get_research_job(db, job_id=job_id)


async def test_steer_running_job_applies_at_next_step_and_shows_in_status(db):
    fake = FakeResearch({"q": ["https://good.example/1", "https://bad.example/2"]})
    fake.search_gate = asyncio.Event()
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        started = await start_research_job(db, query="q", max_urls=2)
        job_id = started["job_id"]
        await asyncio.wait_for(fake.in_search.wait(), 5)

        # Job is mid-search: the steer is recorded but not applied yet.
        steered = await handle_async_agent(
            docs_db=db,
            job_op="steer",
            job_id=job_id,
            steering={"exclude_sources": ["bad.example"], "add_constraints": ["x"]},
        )
        assert "error" not in steered
        assert steered["steer"]["seq"] == 1
        assert steered["steer"]["applied_at"] is None
        assert steered["steer"]["changes"]["exclude_sources"] == ["bad.example"]

        pending = get_research_job(db, job_id=job_id)
        assert pending["steering"][0]["applied_at"] is None
        assert pending["progress"]["step"] == "search"

        fake.search_gate.set()
        status = await _wait_status(db, job_id, {"completed", "failed"})

    assert status["status"] == "completed"
    assert fake.extracted == [["https://good.example/1"]]
    entry = status["steering"][0]
    assert entry["applied_step"] == "extract"
    assert entry["applied_round"] == 1
    assert isinstance(entry["applied_at"], float)
    assert isinstance(entry["at"], float)
    assert status["direction"]["exclude_sources"] == ["bad.example"]
    assert status["direction"]["constraints"] == ["x"]
    assert status["progress"]["step"] == "synthesize"
    assert [s["url"] for s in status["result"]["sources"]] == ["https://good.example/1"]


async def test_steer_rejected_once_job_is_synthesising(db):
    fake = FakeResearch({"q": ["https://a.example/1"]})
    fake.synth_gate = asyncio.Event()
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        job_id = (await start_research_job(db, query="q"))["job_id"]
        await asyncio.wait_for(fake.in_synth.wait(), 5)
        out = steer_research_job(db, job_id=job_id, changes={"add_focus": ["x"]})
        fake.synth_gate.set()
        await _wait_status(db, job_id, {"completed"})
    assert "synthes" in out["error"]
    assert "steering" not in get_research_job(db, job_id=job_id)


async def test_steer_finished_job_is_rejected(db):
    db.create_job(job_id="job_done", query="q")
    db.update_job("job_done", status="completed", result_json='{"markdown": "ok"}')
    out = steer_research_job(db, job_id="job_done", changes={"add_focus": ["x"]})
    assert out["error"].startswith("Error:")
    assert "completed" in out["error"]


async def test_steer_cancelled_or_failed_job_is_rejected(db):
    for status in ("cancelled", "failed"):
        db.create_job(job_id=f"job_{status}", query="q")
        db.update_job(f"job_{status}", status=status)
        out = steer_research_job(
            db, job_id=f"job_{status}", changes={"add_focus": ["x"]}
        )
        assert status in out["error"]


async def test_steer_unknown_job_is_rejected(db):
    out = steer_research_job(db, job_id="job_missing", changes={"add_focus": ["x"]})
    assert "not found" in out["error"]


async def test_steer_invalid_changes_are_rejected(db):
    db.create_job(job_id="job_p", query="q")
    out = steer_research_job(db, job_id="job_p", changes={"depth": 99})
    assert "depth" in out["error"]
    assert "steering" not in get_research_job(db, job_id="job_p")


async def test_steer_sequence_numbers_increase(db):
    db.create_job(job_id="job_p", query="q")
    first = steer_research_job(db, job_id="job_p", changes={"add_focus": ["a"]})
    second = steer_research_job(db, job_id="job_p", changes={"add_focus": ["b"]})
    assert first["steer"]["seq"] == 1
    assert second["steer"]["seq"] == 2
    status = get_research_job(db, job_id="job_p")
    assert [e["seq"] for e in status["steering"]] == [1, 2]
    assert status["direction"]["focus"] == ["a", "b"]


async def test_resume_carries_applied_and_pending_steering(db):
    params = {
        "max_urls": 2,
        "steering": [
            {
                "seq": 1,
                "at": 1.0,
                "changes": {"exclude_sources": ["bad.example"]},
                "applied_at": 2.0,
                "applied_step": "extract",
                "applied_round": 1,
            },
            {
                "seq": 2,
                "at": 3.0,
                "changes": {"add_constraints": ["late"]},
                "applied_at": None,
                "applied_step": None,
                "applied_round": None,
            },
        ],
        "progress": {"step": "extract", "round": 1, "at": 2.0},
    }
    db.create_job(job_id="job_r", query="q", params_json=json.dumps(params))
    db.update_job("job_r", status="failed", error="boom")

    fake = FakeResearch({"q": ["https://bad.example/1", "https://ok.example/2"]})
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        resumed = await resume_research_job(db, job_id="job_r")
        assert resumed["resumed"] is True
        # The row still reads "failed" until the resumed task starts, so wait
        # on the task itself rather than polling the status.
        await asyncio.wait_for(_JOB_TASKS["job_r"], 5)
        status = get_research_job(db, job_id="job_r")

    assert status["status"] == "completed"
    assert fake.extracted == [["https://ok.example/2"]]
    assert "late" in fake.prompts[0]
    late = status["steering"][1]
    assert late["applied_step"] == "search"
    assert late["applied_round"] == 1


async def test_status_without_steering_has_no_steering_fields(db):
    db.create_job(job_id="job_plain", query="q")
    status = get_research_job(db, job_id="job_plain")
    assert "steering" not in status
    assert "direction" not in status
    assert "progress" not in status


async def test_status_tolerates_corrupt_params(db):
    db.create_job(job_id="job_bad", query="q", params_json="{not json")
    status = get_research_job(db, job_id="job_bad")
    assert status["status"] == "pending"
    assert "steering" not in status


async def test_steer_tolerates_corrupt_params(db):
    db.create_job(job_id="job_bad", query="q", params_json="[1, 2]")
    out = steer_research_job(db, job_id="job_bad", changes={"add_focus": ["x"]})
    assert out["steer"]["seq"] == 1


# ---------------------------------------------------------------------------
# DocsDB.update_job_params
# ---------------------------------------------------------------------------


def test_update_job_params_is_read_modify_write(db):
    db.create_job(job_id="job_x", query="q", params_json='{"a": 1}')

    def bump(row, params):
        assert row["status"] == "pending"
        return {**params, "a": params["a"] + 1}

    row = db.update_job_params("job_x", mutate=bump)
    assert json.loads(row["params_json"]) == {"a": 2}
    assert json.loads(db.get_job("job_x")["params_json"]) == {"a": 2}


def test_update_job_params_none_leaves_row_unchanged(db):
    db.create_job(job_id="job_x", query="q", params_json='{"a": 1}')
    row = db.update_job_params("job_x", mutate=lambda row, params: None)
    assert json.loads(row["params_json"]) == {"a": 1}


def test_update_job_params_missing_job_returns_none(db):
    assert db.update_job_params("nope", mutate=lambda row, params: params) is None


def test_update_job_params_rolls_back_on_error(db):
    db.create_job(job_id="job_x", query="q", params_json='{"a": 1}')

    def boom(row, params):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        db.update_job_params("job_x", mutate=boom)
    assert json.loads(db.get_job("job_x")["params_json"]) == {"a": 1}
    # The connection is usable again after the rollback.
    db.update_job("job_x", status="running")
    assert db.get_job("job_x")["status"] == "running"


# ---------------------------------------------------------------------------
# Handler, MCP tool and CLI surfaces
# ---------------------------------------------------------------------------


async def test_handler_steer_requires_job_id_and_changes(db):
    out = await handle_async_agent(docs_db=db, job_op="steer", steering={"depth": 1})
    assert "job_id" in out["error"]
    out = await handle_async_agent(docs_db=db, job_op="steer", job_id="job_x")
    assert "steering" in out["error"]


async def test_handler_unknown_operation_lists_steer(db):
    out = await handle_async_agent(docs_db=db, job_op="bogus")
    assert "steer" in out["error"]


async def test_mcp_extract_tool_routes_steer(db):
    from structured import payload

    from wet import server

    db.create_job(job_id="job_t", query="q")
    with patch.object(server, "_docs_db", db):
        result = await server.extract(
            action="agent",
            job_op="steer",
            job_id="job_t",
            steering={"add_focus": ["x"], "depth": 1},
        )
    data = payload(result)
    assert data["job_id"] == "job_t"
    assert data["steer"]["changes"] == {"add_focus": ["x"], "depth": 1}


def test_cli_steer_builds_changes_from_flags(db, capsys):
    from wet import server
    from wet.cli import main

    db.create_job(job_id="job_c", query="q")
    # The CLI runs the server lifespan in-process, which opens the docs DB.
    with patch.object(server, "make_docs_db", return_value=db):
        code = main(
            [
                "extract",
                "--action",
                "agent",
                "--job-op",
                "steer",
                "--job-id",
                "job_c",
                "--add-focus",
                "pricing",
                "--add-focus",
                "limits",
                "--remove-focus",
                "old",
                "--add-constraint",
                "USD only",
                "--exclude-source",
                "bad.example",
                "--remaining-depth",
                "1",
            ]
        )
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["steer"]["changes"] == {
        "add_focus": ["pricing", "limits"],
        "remove_focus": ["old"],
        "add_constraints": ["USD only"],
        "exclude_sources": ["bad.example"],
        "depth": 1,
    }


def test_cli_steer_without_flags_reports_error(db, capsys):
    from wet import server
    from wet.cli import main

    db.create_job(job_id="job_c", query="q")
    # The CLI runs the server lifespan in-process, which opens the docs DB.
    with patch.object(server, "make_docs_db", return_value=db):
        code = main(
            ["extract", "--action", "agent", "--job-op", "steer", "--job-id", "job_c"]
        )
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert "steering" in out["error"]


async def test_cancelled_job_runner_stops_polling(db):
    """A job cancelled mid-run never applies later steering."""
    fake = FakeResearch({"q": ["https://a.example/1"]})
    fake.search_gate = asyncio.Event()
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        job_id = (await start_research_job(db, query="q"))["job_id"]
        await asyncio.wait_for(fake.in_search.wait(), 5)
        await handle_async_agent(docs_db=db, job_op="cancel", job_id=job_id)
        out = steer_research_job(db, job_id=job_id, changes={"add_focus": ["x"]})
        fake.search_gate.set()
        await asyncio.sleep(0)
    assert "cancelled" in out["error"]


# ---------------------------------------------------------------------------
# Edge cases: bounds, tolerance and cross-process state
# ---------------------------------------------------------------------------


def test_direction_from_dict_ignores_malformed_fields():
    restored = ResearchDirection.from_dict(
        {"focus": "x", "constraints": ["ok", 3], "remaining_depth": 99}
    )
    assert restored.focus == []
    assert restored.constraints == ["ok"]
    assert restored.remaining_depth == ao.MAX_REMAINING_DEPTH


async def test_removing_the_focus_at_the_search_checkpoint_goes_to_synthesis():
    fake = FakeResearch({"q": ["https://a.example/1"]})
    steps: list[tuple[str, int]] = []

    async def on_step(step, round_no, direction):
        steps.append((step, round_no))
        if (step, round_no) == ("extract", 1):
            return apply_steering(direction, {"add_focus": ["x"]})
        if (step, round_no) == ("search", 2):
            return apply_steering(direction, {"remove_focus": ["x"]})
        return direction

    result = await _run(fake, on_step=on_step)
    assert steps == [("search", 1), ("extract", 1), ("search", 2), ("synthesize", 1)]
    assert [q for q, _ in fake.searches] == ["q"]
    assert len(result["sources"]) == 1


async def test_round_with_only_excluded_results_extracts_nothing():
    fake = FakeResearch(
        {"q": ["https://a.example/1"], "q x": ["https://bad.example/9"]}
    )

    async def on_step(step, round_no, direction):
        if (step, round_no) == ("extract", 1):
            return apply_steering(
                direction, {"add_focus": ["x"], "exclude_sources": ["bad.example"]}
            )
        return direction

    result = await _run(fake, on_step=on_step)
    assert [q for q, _ in fake.searches] == ["q", "q x"]
    assert fake.extracted == [["https://a.example/1"]]
    assert [s["url"] for s in result["sources"]] == ["https://a.example/1"]


async def test_rounds_are_capped_even_when_depth_is_steered_up_again():
    topics = [f"t{i}" for i in range(10)]
    fake = FakeResearch({"q": ["https://a.example/1"]})

    async def on_step(step, round_no, direction):
        # Keep topping depth back up to the maximum at every step.
        return apply_steering(
            direction, {"add_focus": topics, "depth": ao.MAX_REMAINING_DEPTH}
        )

    await _run(fake, on_step=on_step)
    assert len(fake.searches) == 1 + ao.MAX_REMAINING_DEPTH


async def test_job_cancelled_by_another_process_stops_at_next_step(db):
    fake = FakeResearch({"q": ["https://a.example/1"]})
    fake.search_gate = asyncio.Event()
    p1, p2, p3, p4 = fake.patches()
    with p1, p2, p3, p4:
        job_id = (await start_research_job(db, query="q"))["job_id"]
        task = _JOB_TASKS[job_id]
        await asyncio.wait_for(fake.in_search.wait(), 5)
        # Another process (for example the CLI) can only mark the row; it has
        # no handle on this process's task.
        db.update_job(job_id, status="cancelled", error="Job cancelled by caller")
        fake.search_gate.set()
        await asyncio.wait_for(task, 5)
    status = get_research_job(db, job_id=job_id)
    assert status["status"] == "cancelled"
    assert fake.extracted == []
    assert fake.prompts == []


async def test_status_and_steer_skip_invalid_stored_steering(db):
    params = {
        "max_urls": 2,
        "steering": [
            {"seq": 1, "at": 1.0, "changes": {"depth": 99}, "applied_at": None},
            "garbage",
            {"seq": 2, "at": 2.0, "changes": {"add_focus": ["ok"]}, "applied_at": None},
        ],
    }
    db.create_job(job_id="job_s", query="q", params_json=json.dumps(params))
    status = get_research_job(db, job_id="job_s")
    assert [e["seq"] for e in status["steering"]] == [1, 2]
    assert status["direction"]["focus"] == ["ok"]
    assert status["direction"]["remaining_depth"] == ao.DEFAULT_REMAINING_DEPTH
    out = steer_research_job(db, job_id="job_s", changes={"add_focus": ["more"]})
    assert out["steer"]["seq"] == 3


async def test_status_tolerates_non_object_params(db):
    db.create_job(job_id="job_list", query="q", params_json="[1, 2]")
    status = get_research_job(db, job_id="job_list")
    assert status["status"] == "pending"
    assert "steering" not in status
    assert "progress" not in status


def test_update_job_params_joins_an_open_transaction(db):
    db.create_job(job_id="job_x", query="q", params_json='{"a": 1}')
    with db._lock:
        db._conn.execute("UPDATE jobs SET query = 'changed' WHERE id = 'job_x'")
        assert db._conn.in_transaction
        db.update_job_params("job_x", mutate=lambda row, params: {"a": 2})
    assert not db._conn.in_transaction
    row = db.get_job("job_x")
    assert row["query"] == "changed"
    assert json.loads(row["params_json"]) == {"a": 2}
