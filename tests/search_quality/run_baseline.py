"""Measure wet's normal search quality through the MCP stdio protocol."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

DEFAULT_QUERY_FILE = Path(__file__).with_name("queries.jsonl")
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}
UNUSABLE_TEXT = re.compile(
    r"^(accept cookies?|cookies?|javascript required|enable javascript)", re.I
)


def load_queries(path: Path) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        item = json.loads(line)
        if not item.get("id") or not item.get("query"):
            raise ValueError(f"query line {line_number} needs id and query")
        if not (item.get("topic_terms") or item.get("expected_domains")):
            raise ValueError(f"query line {line_number} needs scoring metadata")
        queries.append(item)
    if not queries:
        raise ValueError(f"no queries found in {path}")
    return queries


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(query),
            "",
        )
    )


def _text(result: dict[str, Any]) -> str:
    return " ".join(
        str(result.get(key) or "") for key in ("title", "snippet", "content")
    ).strip()


def filter_unusable(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep results with a URL and useful human-readable text."""
    kept: list[dict[str, Any]] = []
    for result in results:
        url = str(result.get("url") or "").strip()
        text = _text(result)
        if not url or len(text) < 20 or UNUSABLE_TEXT.match(text):
            continue
        kept.append(result)
    return kept


def dedupe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by URL while preserving provider order."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for result in results:
        key = _canonical_url(str(result.get("url") or ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(result)
    return unique


def score_one(
    query_spec: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return the stable per-query quality schema used by baseline and after runs."""
    urls = [str(result.get("url") or "").strip() for result in results]
    domains = [urlsplit(url).netloc.lower() for url in urls if url]
    snippets = [str(result.get("snippet") or "").strip() for result in results]
    expected_domains = [
        str(domain).lower() for domain in query_spec.get("expected_domains", [])
    ]
    topic_terms = [str(term).lower() for term in query_spec.get("topic_terms", [])]
    on_topic = 0
    for result in results:
        domain = urlsplit(str(result.get("url") or "").strip()).netloc.lower()
        haystack = _text(result).lower()
        domain_hit = any(
            domain == expected or domain.endswith("." + expected)
            for expected in expected_domains
        )
        topic_hit = any(term in haystack for term in topic_terms)
        on_topic += int(domain_hit or topic_hit)
    canonical_urls = [_canonical_url(url) for url in urls if url]
    usable = filter_unusable(results)
    unique = dedupe(results)
    return {
        "id": query_spec["id"],
        "n_results": len(results),
        "usable_results": len(usable),
        "deduped_results": len(unique),
        "on_topic_hits": on_topic if (expected_domains or topic_terms) else None,
        "duplicate_ratio": 1 - (len(set(canonical_urls)) / len(canonical_urls))
        if canonical_urls
        else 0.0,
        "empty_snippet_ratio": sum(len(snippet) < 40 for snippet in snippets)
        / len(snippets)
        if snippets
        else 1.0,
        "unique_domains": len(set(domains)),
    }


def _payload(result: Any) -> dict[str, Any]:
    for attribute in ("structuredContent", "structured_content"):
        structured = getattr(result, attribute, None)
        if isinstance(structured, dict):
            return structured
    text = "".join(
        getattr(block, "text", "") for block in getattr(result, "content", [])
    )
    if not text:
        raise ValueError("MCP search returned no text content")
    wrapped = re.search(
        r"<untrusted_search_content>\s*(?P<payload>.*?)\s*</untrusted_search_content>",
        text,
        re.DOTALL,
    )
    if wrapped:
        text = wrapped.group("payload")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("MCP search payload is not an object")
    return data


def _server_env(temp_path: Path) -> dict[str, str]:
    """Build an isolated server environment for the search-quality protocol run."""
    env = {
        **os.environ,
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "WARNING"),
        "CACHE_DIR": str(temp_path / "cache"),
        "DOCS_DB_PATH": str(temp_path / "docs.db"),
        "DOWNLOAD_DIR": str(temp_path / "downloads"),
        # Search quality exercises the web-search path, not legacy Drive sync.
        # Blank both values so a stale one-sided local credential cannot prevent
        # server startup after the Drive-to-Cloudflare cutover.
        "GOOGLE_DRIVE_CLIENT_ID": "",
        "GOOGLE_DRIVE_CLIENT_SECRET": "",
    }
    return env


async def run(queries: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    runner_error: str | None = None
    with tempfile.TemporaryDirectory(prefix="wet-search-quality-") as temp_dir:
        temp_path = Path(temp_dir)
        env = _server_env(temp_path)
        params = StdioServerParameters(command="uv", args=["run", "wet-mcp"], env=env)
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    for query_spec in queries:
                        record: dict[str, Any] = {"query": query_spec}
                        try:
                            payload = await session.call_tool(
                                "search",
                                {"action": "search", "query": query_spec["query"]},
                            )
                            data = _payload(payload)
                            raw_results = data.get("results", [])
                            if not isinstance(raw_results, list):
                                raise ValueError(
                                    "MCP search payload has non-list results"
                                )
                            score = score_one(query_spec, raw_results)
                            record.update({"score": score, "results": raw_results})
                        except (
                            Exception
                        ) as exc:  # Keep all query ids visible in a baseline run.
                            record.update(
                                {
                                    "score": score_one(query_spec, []),
                                    "results": [],
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )
                        records.append(record)
        except Exception as exc:
            runner_error = f"{type(exc).__name__}: {exc}"
            records = [
                {
                    "query": query_spec,
                    "score": score_one(query_spec, []),
                    "results": [],
                    "error": runner_error,
                }
                for query_spec in queries
            ]
    scores = [record["score"] for record in records]

    def numeric(key: str) -> list[float]:
        return [score[key] for score in scores if score[key] is not None]

    def avg(key: str) -> float | None:
        values = numeric(key)
        return sum(values) / len(values) if values else None

    return {
        "schema_version": 1,
        "query_file_schema": "id/query/kind/topic_group/topic_terms/expected_domains",
        "n_queries": len(records),
        "n_errors": sum("error" in record for record in records),
        "runner_error": runner_error,
        "aggregate": {
            "avg_on_topic_hits": avg("on_topic_hits"),
            "avg_duplicate_ratio": avg("duplicate_ratio"),
            "avg_empty_snippet_ratio": avg("empty_snippet_ratio"),
            "avg_unique_domains": avg("unique_domains"),
            "total_results": sum(score["n_results"] for score in scores),
            "total_usable_results": sum(score["usable_results"] for score in scores),
            "total_deduped_results": sum(score["deduped_results"] for score in scores),
        },
        "queries": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    queries = load_queries(args.query_file)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        queries = queries[: args.limit]
    result = asyncio.run(run(queries))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
