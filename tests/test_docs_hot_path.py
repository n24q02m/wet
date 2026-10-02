"""Guards for the two hot-path shapes in `sources/docs.py`.

`_strip_nav_heading_blocks` scans the heading index for runs of same-level
headings and, since this change, advances the outer pointer to the index that
broke the run (`i = j`) instead of to the next heading (`i += 1`). That is only
sound because the inner loop's `break` condition does not depend on where the
run started, so every run beginning inside `[i + 1, j - 1]` breaks at the same
`j` and is strictly shorter — never reaching the 5-heading threshold that the
skipped-over run already failed.

The reference below is the pre-change walk. The tests assert the two produce
identical output: exhaustively over alphabets picked to hit every branch of the
inner loop, and over randomly generated documents. Both sweeps run in two sizes
— a fast one by default, and the full 2,222,302-sequence / 60,000-document
version under `-m full`.

`try_llms_txt` uses `lstrip` rather than `strip` before its `<!DOCTYPE` test.
The tests here pin the behaviour that makes the two interchangeable: the guard
must reject an HTML error page no matter how much whitespace precedes the
doctype, which also rules out narrowing the test to a fixed-size prefix of the
body.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.docs import (
    _ANY_HEADING_RE,
    _strip_nav_heading_blocks,
    try_llms_txt,
)


def _reference_strip_nav_heading_blocks(lines: Sequence[str]) -> list[str]:
    """Pre-change implementation, kept only as the equivalence oracle.

    Identical to `_strip_nav_heading_blocks` except that the outer pointer
    advances by one heading when a run is too short to be navigation.
    """
    headings: dict[int, tuple[int, str]] = {}
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            m = _ANY_HEADING_RE.match(stripped)
            if m:
                headings[i] = (len(m.group(1)), m.group(2))

    if len(headings) < 5:
        return list(lines)

    nav_lines: set[int] = set()
    heading_indices = sorted(headings.keys())

    i = 0
    while i < len(heading_indices):
        start_idx = heading_indices[i]
        level = headings[start_idx][0]
        run = [start_idx]

        j = i + 1
        while j < len(heading_indices):
            idx = heading_indices[j]
            if headings[idx][0] != level:
                break
            prev_idx = run[-1]
            content_length = 0
            is_over_length = False
            for k in range(prev_idx + 1, idx):
                content_length += len(lines[k].strip())
                if content_length > 50:
                    is_over_length = True
                    break
            if is_over_length:
                break

            run.append(idx)
            j += 1

        if len(run) >= 5:
            nav_lines.update(run)
            i = j
        else:
            i += 1

    if not nav_lines:
        return list(lines)

    return [line for i, line in enumerate(lines) if i not in nav_lines]


# Symbols chosen so that products over them exercise every inner-loop branch:
# a same-level heading, a different-level heading, empty filler, filler just
# under the 50-char content budget, and filler just over it.
_FAST_ALPHABETS = [
    (["# a", "## a", "", "z" * 60], 8),
    (["# a", "## a", "", "y" * 50, "y" * 51], 6),
]

_FULL_ALPHABETS = [
    (["# a", "## a", "", "z" * 60], 10),
    (["# a", "## a", "", "y" * 50, "y" * 51], 8),
    (["# a", "## a", "### a", "", "  ", "w" * 60], 7),
]

_WORDS = ("Intro", "API", "Guide", "FAQ", "Usage", "Install", "Notes")


def _sweep(alphabets: list[tuple[list[str], int]]) -> int:
    total = 0
    for alphabet, maxlen in alphabets:
        for n in range(1, maxlen + 1):
            for combo in itertools.product(alphabet, repeat=n):
                lines = list(combo)
                total += 1
                assert _strip_nav_heading_blocks(lines) == (
                    _reference_strip_nav_heading_blocks(lines)
                ), f"divergence on {lines!r}"
    return total


def _gen_navlike(rng: random.Random, n: int) -> list[str]:
    """Many headings at varying levels, mostly short or blank content between."""
    out: list[str] = []
    while len(out) < n:
        r = rng.random()
        if r < 0.55:
            level = rng.randint(1, 6)
            out.append("#" * level + " " + rng.choice(_WORDS) + str(rng.randint(0, 9)))
        elif r < 0.75:
            out.append("")
        elif r < 0.9:
            out.append("x" * rng.randint(1, 25))
        else:
            out.append("y" * rng.randint(40, 120))
    return out


def _gen_runs(rng: random.Random, n: int) -> list[str]:
    """Explicit heading runs of length 1..8, separated by filler either side of
    the 50-char content budget."""
    out: list[str] = []
    while len(out) < n:
        level = rng.randint(1, 6)
        for _ in range(rng.randint(1, 8)):
            out.append("#" * level + " " + rng.choice(_WORDS))
            for _ in range(rng.choice([0, 1, 2, 3])):
                out.append(rng.choice(["", "  ", "a" * rng.randint(1, 30), "b" * 60]))
    return out


def _random_sweep(cases: int) -> None:
    rng = random.Random(4242)
    for iteration in range(cases):
        gen = _gen_navlike if iteration % 2 else _gen_runs
        lines = gen(rng, rng.randint(0, 60))
        assert _strip_nav_heading_blocks(lines) == (
            _reference_strip_nav_heading_blocks(lines)
        ), f"divergence on {lines!r}"


class TestNavStripBehaviour:
    def test_five_same_level_headings_are_stripped(self):
        lines = ["## " + w for w in ("A", "B", "C", "D", "E")]
        assert _strip_nav_heading_blocks(lines) == []

    def test_four_same_level_headings_are_kept(self):
        lines = ["## A", "## B", "## C", "## D", "# E"]
        assert _strip_nav_heading_blocks(lines) == lines

    def test_prose_between_headings_breaks_the_run(self):
        body = "This paragraph is comfortably longer than the fifty character budget."
        lines = ["## A", body, "## B", body, "## C", body, "## D", body, "## E"]
        assert _strip_nav_heading_blocks(lines) == lines

    def test_run_after_a_short_run_is_still_stripped(self):
        """A short leading run must not mask the navigation block behind it."""
        long_body = "x" * 80
        lines = ["# A", "# B", long_body] + ["## " + c for c in "CDEFG"]
        assert _strip_nav_heading_blocks(lines) == ["# A", "# B", long_body]


class TestNavStripEquivalence:
    def test_exhaustive_small(self):
        """Every sequence over the fast alphabets matches the reference walk."""
        assert _sweep(_FAST_ALPHABETS) == 106_910

    @pytest.mark.full
    @pytest.mark.timeout(1800)
    def test_exhaustive_full(self):
        """The full sweep: 2,222,302 sequences over three alphabets."""
        assert _sweep(_FULL_ALPHABETS) == 2_222_302

    def test_random_documents(self):
        _random_sweep(3_000)

    @pytest.mark.full
    @pytest.mark.timeout(600)
    def test_random_documents_full(self):
        _random_sweep(60_000)


async def _fetch(body: str) -> str | None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = body

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("wet_mcp.sources.docs._safe_httpx_client", return_value=mock_client):
        return await try_llms_txt("https://example.com/docs")


class TestLlmsTxtDoctypeGuard:
    @pytest.mark.parametrize("padding", [0, 1, 91, 92, 100, 500])
    async def test_rejects_html_page_behind_any_leading_whitespace(self, padding):
        """Leading whitespace must not smuggle an error page past the guard.

        A rendered 404 served with an XML declaration or a pretty-printer's
        indentation can carry an arbitrary run of whitespace before the
        doctype. Sizes either side of 91 are pinned because a guard that
        inspects only the first 100 characters starts passing at 92 —
        `len("<!DOCTYPE") == 9`.
        """
        body = " " * padding + "<!DOCTYPE html>\n<html><body>404</body></html>\n" * 20
        assert await _fetch(body) is None

    async def test_rejects_html_page_behind_leading_newlines(self):
        body = "\n" * 300 + "<!DOCTYPE html>\n<html><body>404</body></html>\n" * 20
        assert await _fetch(body) is None

    async def test_accepts_document_with_leading_and_trailing_whitespace(self):
        body = "\n\n# Library\n\n" + ("Documentation content. " * 20) + "\n"
        assert await _fetch(body) == body
