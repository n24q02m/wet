"""12-point health and configuration diagnostics for `wet doctor` (WET-18, WET-36)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wet.config import settings
from wet.runtime import hull_settings, sub_root, wet_config_dir, wet_config_path
from wet.sources.provider_registry import serp_scrape_allowed
from wet.sources.search_backends import (
    chain_backend_names,
    has_uvx_runnable_backend,
    search_backends_with_skips,
)
from wet.transport_check import is_uvx_tool_venv


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One diagnostic probe in the 12-point wet doctor check."""

    id: str
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    hint: str = ""


def _check_python_runtime() -> DoctorCheck:
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = (3, 11) <= (sys.version_info.major, sys.version_info.minor) < (3, 16)
    return DoctorCheck(
        id="python_runtime",
        name="Python runtime (3.11-3.15)",
        status="ok" if ok else "warn",
        detail=f"Python {ver} ({sys.executable})",
        hint="" if ok else "Use Python 3.11-3.15 for full dependency compatibility.",
    )


def _check_profile_dir() -> DoctorCheck:
    try:
        cfg_dir = wet_config_dir()
        cfg_file = wet_config_path()
        return DoctorCheck(
            id="profile_state_dir",
            name="Profile & state directory",
            status="ok",
            detail=f"dir={cfg_dir} config_exists={cfg_file.is_file()}",
        )
    except Exception as exc:
        return DoctorCheck(
            id="profile_state_dir",
            name="Profile & state directory",
            status="fail",
            detail=str(exc),
            hint="Verify WET_PROFILE and filesystem permissions for ~/.n24q02m/wet/.",
        )


def _check_hull_config() -> DoctorCheck:
    try:
        hs = hull_settings()
        return DoctorCheck(
            id="hull_config",
            name="Hull auth & bind configuration",
            status="ok",
            detail=f"auth={hs.server.auth} bind={hs.server.host}:{hs.server.port}",
        )
    except Exception as exc:
        return DoctorCheck(
            id="hull_config",
            name="Hull auth & bind configuration",
            status="fail",
            detail=str(exc),
            hint="Fix config.toml syntax or run `wet config init`.",
        )


def _check_sqlite_fts5() -> DoctorCheck:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _fts_probe USING fts5(x)")
        conn.close()
        return DoctorCheck(
            id="sqlite_fts5",
            name="SQLite + FTS5 support",
            status="ok",
            detail=f"sqlite {sqlite3.sqlite_version} with FTS5 enabled",
        )
    except Exception as exc:
        return DoctorCheck(
            id="sqlite_fts5",
            name="SQLite + FTS5 support",
            status="fail",
            detail=str(exc),
            hint="Python sqlite3 build must include FTS5.",
        )


def _check_sqlite_vec() -> DoctorCheck:
    spec = importlib.util.find_spec("sqlite_vec")
    return DoctorCheck(
        id="sqlite_vec",
        name="sqlite-vec extension",
        status="ok" if spec is not None else "warn",
        detail="available"
        if spec is not None
        else "sqlite_vec not installed (FTS5 fallback active)",
    )


def _check_docs_db_and_alembic() -> DoctorCheck:
    db_path = Path(settings.get_db_path())
    if not db_path.exists():
        return DoctorCheck(
            id="docs_db",
            name="Docs SQLite DB & migrations",
            status="ok",
            detail=f"not yet initialized at {db_path} (will initialize on start)",
        )
    try:
        conn = sqlite3.connect(str(db_path))
        rev_row = conn.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        libs = conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0]
        conn.close()
        rev = rev_row[0] if rev_row else "unstamped"
        return DoctorCheck(
            id="docs_db",
            name="Docs SQLite DB & migrations",
            status="ok",
            detail=f"path={db_path} revision={rev} libraries={libs} chunks={chunks}",
        )
    except Exception as exc:
        return DoctorCheck(
            id="docs_db",
            name="Docs SQLite DB & migrations",
            status="warn",
            detail=f"{db_path}: {exc}",
        )


def _check_web_cache() -> DoctorCheck:
    enabled = bool(settings.wet_cache)
    cache_path = sub_root() / "cache.db" if enabled else None
    return DoctorCheck(
        id="web_cache",
        name="Web cache & diff store",
        status="ok",
        detail=f"enabled={enabled} path={cache_path}",
    )


def _check_search_chain() -> DoctorCheck:
    requested = chain_backend_names()
    backends, skipped = search_backends_with_skips()
    active_names = [b.name for b in backends]
    status = "ok" if active_names else "warn"
    return DoctorCheck(
        id="search_chain",
        name="Search backend chain",
        status=status,
        detail=f"requested={requested} active={active_names} skipped={list(skipped.keys())}",
        hint=""
        if active_names
        else "Configure an API key, SEARXNG_URL, or use keenable/firecrawl.",
    )


def _check_serp_policy() -> DoctorCheck:
    allowed = serp_scrape_allowed()
    return DoctorCheck(
        id="serp_scrape_policy",
        name="SERP scrape policy (WET_ALLOW_SERP_SCRAPE)",
        status="ok",
        detail=f"WET_ALLOW_SERP_SCRAPE={allowed} (default=False keeps keyless non-SERP active)",
    )


def _check_uvx_transport() -> DoctorCheck:
    uvx = is_uvx_tool_venv()
    runnable = has_uvx_runnable_backend()
    ok = (not uvx) or runnable
    return DoctorCheck(
        id="uvx_transport",
        name="Runtime transport & uvx parity",
        status="ok" if ok else "warn",
        detail=f"uvx_tool_venv={uvx} uvx_runnable_search={runnable}",
        hint=""
        if ok
        else "Set SEARCH_BACKENDS=keenable,firecrawl or provide a search API key.",
    )


def _check_browser_runtime() -> DoctorCheck:
    spec = importlib.util.find_spec("patchright") or importlib.util.find_spec(
        "playwright"
    )
    disabled = bool(getattr(settings, "disable_local_browser", False))
    detail = (
        "local browser disabled (WET_DISABLE_LOCAL_BROWSER)"
        if disabled
        else (
            "browser package present"
            if spec is not None
            else "patchright/playwright missing (HTTP extract only)"
        )
    )
    return DoctorCheck(
        id="browser_runtime",
        name="Headless browser fallback",
        status="ok" if (disabled or spec is not None) else "warn",
        detail=detail,
    )


def _check_embeddings_rerank() -> DoctorCheck:
    fastretrieval = importlib.util.find_spec("fastretrieval") is not None
    openrouter = bool(settings.openrouter_api_key)
    return DoctorCheck(
        id="embeddings_rerank",
        name="Local embeddings & reranker",
        status="ok" if (fastretrieval or openrouter) else "warn",
        detail=f"fastretrieval={fastretrieval} openrouter_key={openrouter}",
        hint=""
        if (fastretrieval or openrouter)
        else "Install fastretrieval or configure [models.embed] for semantic docs search.",
    )


def run_doctor() -> dict[str, Any]:
    """Run all 12 diagnostic checks and return a structured health report."""
    checks = [
        _check_python_runtime(),
        _check_profile_dir(),
        _check_hull_config(),
        _check_sqlite_fts5(),
        _check_sqlite_vec(),
        _check_docs_db_and_alembic(),
        _check_web_cache(),
        _check_search_chain(),
        _check_serp_policy(),
        _check_uvx_transport(),
        _check_browser_runtime(),
        _check_embeddings_rerank(),
    ]
    fail_count = sum(1 for c in checks if c.status == "fail")
    warn_count = sum(1 for c in checks if c.status == "warn")
    overall = "fail" if fail_count > 0 else ("warn" if warn_count > 0 else "ok")
    return {
        "status": overall,
        "total_checks": len(checks),
        "failures": fail_count,
        "warnings": warn_count,
        "checks": [asdict(c) for c in checks],
    }
