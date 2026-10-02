"""Run docs search benchmark directly (no MCP server needed).

Usage:
    cd wet-mcp
    uv run --no-sync python tests/run_benchmark.py [--start N] [--end N] [--ids id1,id2]

Outputs a compact summary per library and a final table.
Results are saved incrementally (after each library) to avoid data loss.
"""

import asyncio
import io
import json
import os
import sys
import time
import warnings
from typing import Any

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(_s, io.TextIOWrapper):
            _s.reconfigure(encoding="utf-8", errors="replace")

# Suppress noisy ResourceWarnings from SearXNG subprocess cleanup
warnings.filterwarnings("ignore", category=ResourceWarning)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from benchmark_docs_search import BENCHMARK_CASES  # noqa: E402


async def run_single(case: dict, docs_db, embed_fn, embed_batch_fn, rerank_fn):
    """Run a single benchmark case and return results dict."""
    from wet_mcp.server import _fetch_and_chunk_docs
    from wet_mcp.sources.docs import (
        DISCOVERY_VERSION,
        _normalize_docs_url,
        discover_library,
    )

    library = case["library"]
    query = case["query"]
    case_id = case["id"]
    language = case.get("language")
    limit = 5

    t0 = time.time()

    # Build library identity — include language for DB disambiguation
    lib_key = f"{library}:{language.lower()}" if language else library

    # Check cache
    lib = docs_db.get_library(lib_key)
    if lib:
        cached_version = lib.get("discovery_version", 0)
        if cached_version < DISCOVERY_VERSION:
            lib = None

    if lib:
        ver = docs_db.get_best_version(lib["id"])
        if ver and ver.get("chunk_count", 0) > 0:
            query_embedding = await embed_fn(query, is_query=True) if embed_fn else None
            results = docs_db.search(
                query=query,
                library_name=lib_key,
                limit=limit * 3,
                query_embedding=query_embedding,
            )
            if rerank_fn and len(results) > limit:
                results = await rerank_fn(query, results, limit)
            else:
                results = results[:limit]
            elapsed = time.time() - t0
            return {
                "id": case_id,
                "library": library,
                "source": "cached",
                "docs_url": ver.get("docs_url", ""),
                "pages": 0,
                "chunks": ver.get("chunk_count", 0),
                "results": results,
                "elapsed": elapsed,
            }

    # Discover
    discovery = await discover_library(library, language=language)
    docs_url = ""
    repo_url = ""

    if discovery:
        docs_url = discovery.get("homepage", "")
        repo_url = discovery.get("repository", "")
        registry = discovery.get("registry", "")
        description = discovery.get("description", "")
    else:
        registry = ""
        description = ""

    if not docs_url:
        # Fallback: use GitHub repo URL as docs source if available
        if repo_url and "github.com" in repo_url:
            docs_url = repo_url
        else:
            # SearXNG fallback disabled in benchmark mode: subprocess
            # management conflicts with Python 3.13 asyncio on Windows.
            # In production, server.py handles SearXNG discovery.
            elapsed = time.time() - t0
            return {
                "id": case_id,
                "library": library,
                "source": "NOT_FOUND",
                "docs_url": "",
                "pages": 0,
                "chunks": 0,
                "results": [],
                "elapsed": elapsed,
            }

    # Upsert
    lib_id = docs_db.upsert_library(
        name=lib_key,
        docs_url=docs_url,
        registry=registry,
        description=description,
    )
    ver_id = docs_db.upsert_version(
        library_id=lib_id,
        version="latest",
        docs_url=docs_url,
    )
    docs_db.clear_version_chunks(ver_id)

    # Normalize URL
    docs_url = _normalize_docs_url(docs_url)

    # Fetch & chunk
    all_chunks, page_count = await _fetch_and_chunk_docs(
        docs_url=docs_url,
        repo_url=repo_url,
        query=query,
        library_hint=library,
    )

    # NOTE: SearXNG "few pages" fallback (post-fetch quality gate) is
    # skipped in benchmark mode as it mirrors the initial discovery only.
    # The per-library SearXNG discovery fallback above handles NOT_FOUND.

    if not all_chunks:
        elapsed = time.time() - t0
        return {
            "id": case_id,
            "library": library,
            "source": "NO_CONTENT",
            "docs_url": docs_url,
            "pages": page_count,
            "chunks": 0,
            "results": [],
            "elapsed": elapsed,
        }

    # Determine source tier
    if page_count == 1 and len(all_chunks) > 20:
        source = "llms.txt"
    elif any("github.com" in (c.get("url", "") or "") for c in all_chunks[:3]):
        source = "gh_raw"
    else:
        source = "crawl"

    # Embeddings
    embeddings = None
    if embed_batch_fn:
        texts = []
        for c in all_chunks:
            parts = []
            if c.get("title"):
                parts.append(c["title"])
            if c.get("heading_path") and c.get("heading_path") != c.get("title"):
                parts.append(c["heading_path"])
            parts.append(c["content"])
            texts.append(" | ".join(parts)[:2000])
        embeddings = await embed_batch_fn(texts)

    # Store
    docs_db.add_chunks(
        version_id=ver_id,
        library_id=lib_id,
        chunks=all_chunks,
        embeddings=embeddings,
    )
    docs_db.mark_version_indexed(ver_id, page_count, len(all_chunks))

    # Search
    query_embedding = await embed_fn(query, is_query=True) if embed_fn else None
    results = docs_db.search(
        query=query,
        library_name=lib_key,
        limit=limit * 3,
        query_embedding=query_embedding,
    )
    if rerank_fn and len(results) > limit:
        results = await rerank_fn(query, results, limit)
    else:
        results = results[:limit]

    elapsed = time.time() - t0
    return {
        "id": case_id,
        "library": library,
        "source": source,
        "docs_url": docs_url,
        "pages": page_count,
        "chunks": len(all_chunks),
        "results": results,
        "elapsed": elapsed,
    }


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=len(BENCHMARK_CASES))
    parser.add_argument("--ids", type=str, default="")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-index by deleting the benchmark DB before running",
    )
    args = parser.parse_args()

    # Select cases
    if args.ids:
        ids = [x.strip() for x in args.ids.split(",")]
        cases = [c for c in BENCHMARK_CASES if c["id"] in ids]
    else:
        cases = BENCHMARK_CASES[args.start : args.end]

    print(f"Running {len(cases)} benchmark cases...")
    print("=" * 80)

    # Init DB (use separate benchmark DB to avoid conflicts)
    from wet_mcp.config import settings
    from wet_mcp.db import DocsDB

    db_path = settings.get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Force re-index: delete existing DB to start fresh
    if args.force and db_path.exists():
        db_path.unlink()
        print(f"Deleted existing DB: {db_path}")

    docs_db = DocsDB(db_path, embedding_dims=768)

    # Pre-load crawl4ai
    print("Pre-loading Crawl4AI...")
    await asyncio.to_thread(__import__, "crawl4ai")

    # Try init embedding
    embed_fn = None
    embed_batch_fn = None
    rerank_fn = None
    try:
        from wet_mcp.embedder import get_backend, init_backend

        backend = init_backend("local", None)
        ndims = await backend.check_available()
        if ndims > 0:
            print(f"Embedding: local ONNX (dims={ndims})")

            async def _embed(text, is_query=False):
                from wet_mcp.embedder import LocalEmbeddingBackend

                b = get_backend()
                if not b:
                    return None
                t = text
                if is_query and isinstance(b, LocalEmbeddingBackend):
                    t = f"Instruct: Retrieve relevant technical documentation\nQuery: {text}"
                vec = await b.embed_single(t, 768)
                return vec[:768] if len(vec) > 768 else vec

            async def _embed_batch(texts):
                b = get_backend()
                if not b:
                    return None
                vecs = await b.embed_texts(texts, 768)
                return [v[:768] if len(v) > 768 else v for v in vecs]

            embed_fn = _embed
            embed_batch_fn = _embed_batch
    except Exception as e:
        print(f"No embedding backend: {e}")

    # Output path for incremental save
    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.jsonl")

    # Load existing IDs to skip duplicates (unless --force or --ids)
    existing_ids: set[str] = set()
    rerun_ids: set[str] = set()
    if os.path.exists(out_path) and not args.force:
        case_ids = {c["id"] for c in cases}
        kept_lines: list[str] = []
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    row = json.loads(line_s)
                    rid = row["id"]
                except (json.JSONDecodeError, KeyError):
                    kept_lines.append(line_s)
                    continue

                if args.ids and rid in case_ids:
                    # When using --ids, remove old results for those IDs
                    # so they get re-run
                    rerun_ids.add(rid)
                    continue

                existing_ids.add(rid)
                kept_lines.append(line_s)

        # Rewrite file without the IDs we want to re-run
        if rerun_ids:
            with open(out_path, "w", encoding="utf-8") as f:
                for line_s in kept_lines:
                    f.write(line_s + "\n")
            print(
                f"Removed {len(rerun_ids)} old results for re-run: {sorted(rerun_ids)}"
            )

    # Filter out already-completed cases
    cases = [c for c in cases if c["id"] not in existing_ids]
    if not cases:
        print("All cases already have results. Nothing to run.")
        return

    skipped = len(existing_ids)
    if skipped:
        print(
            f"Skipping {skipped} existing results, running {len(cases)} remaining cases"
        )

    def _save_result(result: dict):
        """Save a single result to JSONL incrementally."""
        slim = {**result}
        slim["results"] = [
            {k: v for k, v in res.items() if k != "content"}
            for res in (result.get("results") or [])
        ]
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    # Run benchmarks
    summary: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        idx = args.start + i + 1
        print(f"\n[{idx}/{args.start + len(cases)}] {case['id']} ({case['library']})")
        print(f"  Query: {case['query']}")
        try:
            result = await asyncio.wait_for(
                run_single(case, docs_db, embed_fn, embed_batch_fn, rerank_fn),
                timeout=180,
            )
            # Print compact result
            print(
                f"  Source: {result['source']} | Pages: {result['pages']} | "
                f"Chunks: {result['chunks']} | Time: {result['elapsed']:.1f}s"
            )
            print(f"  URL: {result['docs_url']}")
            if result["results"]:
                for j, r in enumerate(result["results"][:3]):
                    title = (r.get("title") or "")[:50]
                    url = (r.get("url") or "")[:75]
                    score = r.get("score", 0)
                    print(f"    [{j + 1}] score={score} | {title} | {url}")
            else:
                print("    NO RESULTS")
            summary.append(result)
            _save_result(result)
        except (TimeoutError, asyncio.CancelledError):
            print("  TIMEOUT (180s)")
            r = {
                "id": case["id"],
                "library": case["library"],
                "source": "TIMEOUT",
                "docs_url": "",
                "pages": 0,
                "chunks": 0,
                "results": [],
                "elapsed": 180,
            }
            summary.append(r)
            _save_result(r)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback

            traceback.print_exc()
            r = {
                "id": case["id"],
                "library": case["library"],
                "source": "ERROR",
                "docs_url": str(e),
                "pages": 0,
                "chunks": 0,
                "results": [],
                "elapsed": 0,
            }
            summary.append(r)
            _save_result(r)

    # Final summary table
    print("\n" + "=" * 80)
    print(
        f"{'#':<3} {'ID':<20} {'Source':<10} {'Pg':<4} {'Ch':<6} {'Time':<6} {'Top URL'}"
    )
    print("-" * 80)
    for i, r in enumerate(summary):
        top_url = ""
        if r["results"]:
            top_url = (r["results"][0].get("url") or "")[:40]
        print(
            f"{i + 1:<3} {r['id']:<20} {r['source']:<10} "
            f"{r['pages']:<4} {r['chunks']:<6} {r['elapsed']:<6.0f} {top_url}"
        )

    print(f"\nResults saved to {out_path}")

    # Cleanup
    docs_db.close()
    try:
        from wet_mcp.searxng_runner import stop_searxng

        stop_searxng()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
