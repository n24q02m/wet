"""Tier 1 curated library warmup — metadata-only seeding on first startup.

Reads the bundled ``data/tier1_libraries.json`` and seeds library
metadata (id, canonical_name, homepage, github_url, package_managers,
tier=1) into ``DocsDB`` so ``docs_resolve`` can return curated entries
even before any docs are ingested. Actual chunk ingestion is deferred
to:

* ``ingest_tier2`` triggered lazily by the first ``docs_query`` call
  for that library, OR
* ``scripts/build_tier1_index.py`` which eagerly walks the curated list
  via the web-core ``library_docs_strategy`` (Task 10) on a weekly cron.

Freshness: a library is considered "warm" when its
``metadata_seeded_at`` is within 7 days (spec section 3 Tier 1 freshness
target). ``maybe_warm(force=True)`` re-seeds metadata regardless. The gate
deliberately does *not* read ``last_indexed_at``: that column means "chunks
landed", which seeding never does, so keying off it made the warmup's own
write satisfy its own freshness check.
"""

from __future__ import annotations

import json
import time
from importlib.resources import files
from typing import Any

from loguru import logger

# Spec section 3 — Tier 1 must be re-validated within 7 days.
_FRESHNESS_WINDOW_SECONDS = 7 * 24 * 60 * 60


def _load_tier1_payload() -> dict:
    """Load the bundled tier1_libraries.json via importlib.resources."""
    try:
        resource = files("wet_mcp.data").joinpath("tier1_libraries.json")
        return json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        logger.debug(f"Tier 1 fixture not bundled: {exc}")
        return {"libraries": []}


def maybe_warm(db: Any, force: bool = False) -> dict:
    """Seed Tier 1 library metadata into DocsDB. Returns a summary dict.

    Args:
        db: DocsDB instance (post-migration).
        force: If True, re-seed every entry regardless of freshness.

    Returns:
        ``{"total": int, "skipped_fresh": int, "seeded": int}``
    """
    payload = _load_tier1_payload()
    libraries = payload.get("libraries", [])
    if not libraries:
        return {"total": 0, "skipped_fresh": 0, "seeded": 0}

    now = time.time()
    seeded = 0
    skipped_fresh = 0
    for entry in libraries:
        name = entry["id"]
        existing = db.get_library(name)
        if (
            not force
            and existing
            and existing.get("metadata_seeded_at")
            and (now - existing["metadata_seeded_at"]) < _FRESHNESS_WINDOW_SECONDS
        ):
            skipped_fresh += 1
            continue

        try:
            lib_id = db.upsert_library(
                name=name,
                canonical_name=entry.get("canonical_name", name),
                homepage=entry.get("homepage"),
                github_url=entry.get("github_url"),
                package_managers=entry.get("package_managers"),
                tier=1,
            )
            db.mark_metadata_seeded(lib_id)
            seeded += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Tier 1 warmup failed for {name}: {exc}")

    if seeded:
        logger.info(
            f"Tier 1 warmup: seeded {seeded} libraries "
            f"(skipped {skipped_fresh} fresh, total {len(libraries)})"
        )
    return {
        "total": len(libraries),
        "skipped_fresh": skipped_fresh,
        "seeded": seeded,
    }
