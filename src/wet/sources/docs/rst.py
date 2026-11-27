"""reStructuredText to Markdown conversion helpers."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# RST to Markdown (basic conversion for GitHub raw docs)
# ---------------------------------------------------------------------------

# RST heading underline characters (in decreasing priority)
_RST_HEADING_CHARS = set("=-~^\"'+`:._;,#*!?/\\|")

# RST directive pattern: .. directive:: args
_RST_DIRECTIVE_RE = re.compile(r"^\.\.\s+(\w[\w-]*)::(.*)$")
# RST role pattern: :role:`text`
_RST_ROLE_RE = re.compile(r":(\w+):`([^`]*)`")
# RST substitution: |text|
_RST_SUBST_RE = re.compile(r"\|(\w[\w\s]*)\|")


def _process_rst_heading(i: int, line: str, lines: list[str], out: list[str]) -> int:
    underline_char = lines[i + 1].strip()[0]
    if underline_char == "=":
        level = "#"
    elif underline_char == "-":
        level = "##"
    elif underline_char == "~":
        level = "###"
    else:
        level = "####"

    if i > 0 and out:
        prev_stripped = out[-1].strip()
        # The previous line is an overline for this heading if it is one
        # character repeated, and that character is an RST heading rule.
        # Tested via string multiplication to avoid set allocation.
        if (
            prev_stripped
            and prev_stripped[0] * len(prev_stripped) == prev_stripped
            and prev_stripped[0] in _RST_HEADING_CHARS
        ):
            out[-1] = ""

    out.append(f"{level} {line.strip()}")
    return i + 2


def _process_rst_directive(
    i: int,
    lines: list[str],
    out: list[str],
    directive_match: re.Match,
) -> tuple[int, bool, int]:
    directive = directive_match.group(1).lower()
    args = directive_match.group(2).strip()
    in_code_block = False
    code_indent = 0

    if directive in ("code-block", "code", "sourcecode", "highlight"):
        lang = args or ""
        out.append(f"```{lang}")
        i += 1
        while i < len(lines) and (
            not lines[i].strip() or lines[i].strip().startswith(":")
        ):
            i += 1
        if i < len(lines):
            code_indent = len(lines[i]) - len(lines[i].lstrip())
            if code_indent < 2:
                code_indent = 3
        in_code_block = True
    elif directive in (
        "literalinclude",
        "image",
        "figure",
        "raw",
        "include",
        "toctree",
        "contents",
        "moduleauthor",
        "sectionauthor",
        "meta",
        "deprecated",
    ):
        i += 1
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith("   ")):
            i += 1
    elif directive in ("note", "warning", "tip", "important", "seealso"):
        out.append(f"> **{directive.title()}:** {args}")
        i += 1
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith("   ")):
            body = lines[i].strip()
            if body:
                out.append(f"> {body}")
            i += 1
    else:
        i += 1
        while i < len(lines) and lines[i].strip().startswith(":"):
            i += 1

    return i, in_code_block, code_indent


def _rst_to_markdown(content: str) -> str:
    """Convert RST content to rough Markdown for indexing.

    Not a full parser — handles the most common patterns:
    - Headings (underlined titles)
    - Code blocks (``.. code-block::``, ``.. code::``, literal blocks)
    - Cross-references (`:ref:`, `:doc:`, `:class:`, etc.)
    - Directives (stripped except code blocks)
    - Bold/italic/code inline markup
    """
    if not content:
        return ""

    lines = content.split("\n")
    out: list[str] = []
    i = 0
    in_code_block = False
    code_indent = 0

    while i < len(lines):
        line = lines[i]

        # Handle literal blocks (indented after ::)
        if in_code_block:
            stripped = line.strip()
            if stripped and not line.startswith(" " * code_indent) and not line == "":
                # End of indented block
                in_code_block = False
                out.append("```")
                out.append("")
                # Don't increment — reprocess this line
                continue
            out.append(line)
            i += 1
            continue

        # Detect RST headings: line followed by underline of same length
        line_stripped = line.strip()
        if i + 1 < len(lines) and line_stripped:
            next_stripped = lines[i + 1].strip()
            # An RST underline is one character repeated to at least the width
            # of the title, and that character is an RST heading rule.
            # Tested via string multiplication to avoid set allocation.
            if (
                len(next_stripped) >= len(line_stripped)
                and next_stripped
                and next_stripped[0] * len(next_stripped) == next_stripped
                and next_stripped[0] in _RST_HEADING_CHARS
            ):
                i = _process_rst_heading(i, line, lines, out)
                continue

        # Detect code-block directive
        directive_match = _RST_DIRECTIVE_RE.match(line.strip())
        if directive_match:
            i, in_code_block, code_indent = _process_rst_directive(
                i, lines, out, directive_match
            )
            continue

        # Detect literal block ending with ::
        if line.rstrip().endswith("::"):
            out.append(line.rstrip()[:-2] + ":" if len(line.rstrip()) > 2 else "")
            i += 1
            # Skip blank lines
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                code_indent = len(lines[i]) - len(lines[i].lstrip())
                if code_indent < 2:
                    code_indent = 3
                out.append("```")
                in_code_block = True
            continue

        # Process inline RST markup
        processed = line
        # :role:`text` → `text`
        processed = _RST_ROLE_RE.sub(r"`\2`", processed)
        # ``code`` → `code`
        processed = processed.replace("``", "`")
        out.append(processed)
        i += 1

    if in_code_block:
        out.append("```")

    return "\n".join(out)
