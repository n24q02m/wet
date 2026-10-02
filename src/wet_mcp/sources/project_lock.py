"""Project manifest detection + lock builder for Cabinets isolation.

Walks a project root and detects supported manifests (pyproject.toml,
package.json, go.mod, Cargo.toml). Returns a flat list of
``{"id": <library-name>, "version": <version-spec-or-pin>}`` entries
suitable for storing in ``DocsDB.upsert_project_context``.

Detection scope is intentionally minimal — top-level dependencies only.
Lock files (uv.lock, poetry.lock, package-lock.json, Cargo.lock) are
out of scope for v1; we use what the human-authored manifest declares
because Cabinets is a hint, not a SAT solver.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from loguru import logger

# pyproject.toml ---------------------------------------------------------

_PEP508_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _parse_pep508(spec: str) -> tuple[str, str]:
    """Return ``(name, version_spec)`` from a PEP 508 dependency string.

    Handles common forms:

    * ``"fastapi>=0.110"`` → ``("fastapi", ">=0.110")``
    * ``"requests"`` → ``("requests", "")``
    * ``"pydantic[email]>=2.0"`` → ``("pydantic", ">=2.0")``
    """
    spec = spec.strip()
    match = _PEP508_NAME_RE.match(spec)
    if not match:
        return ("", "")
    name = match.group(1)
    rest = spec[match.end() :]
    # Strip optional extras `[...]`
    rest = re.sub(r"^\[[^\]]*\]", "", rest).strip()
    return (name, rest)


def _detect_pyproject(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to parse {path}: {exc}")
        return out

    # PEP 621
    project = data.get("project", {}) or {}
    for dep in project.get("dependencies", []) or []:
        name, version = _parse_pep508(dep)
        if name:
            out.append({"id": name.lower(), "version": version})

    # Poetry
    poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
    for name, value in (poetry.get("dependencies", {}) or {}).items():
        if name.lower() == "python":
            continue
        if isinstance(value, str):
            out.append({"id": name.lower(), "version": value})
        elif isinstance(value, dict):
            out.append({"id": name.lower(), "version": value.get("version", "")})
    return out


# package.json -----------------------------------------------------------


def _detect_package_json(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to parse {path}: {exc}")
        return out
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(key, {}) or {}
        for name, version in deps.items():
            if name.startswith("@types/"):
                continue
            out.append({"id": name.lower(), "version": str(version)})
    return out


# go.mod -----------------------------------------------------------------

_GO_REQUIRE_LINE = re.compile(r"^\s*([\w./\-]+)\s+(v[\w.\-+]+)")


def _detect_go_mod(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        logger.debug(f"Failed to read {path}: {exc}")
        return out
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line.startswith(")"):
            in_block = False
            continue
        if in_block or line.startswith("require "):
            target = line[len("require ") :] if line.startswith("require ") else line
            target = target.strip()
            # Strip trailing comment
            if "//" in target:
                target = target.split("//", 1)[0].strip()
            match = _GO_REQUIRE_LINE.match(target)
            if match:
                name = match.group(1)
                version = match.group(2)
                # Strip github.com/ prefix; keep the org/repo (per spec example).
                short = (
                    name[len("github.com/") :]
                    if name.startswith("github.com/")
                    else name
                )
                out.append({"id": short.lower(), "version": version})
    return out


# Cargo.toml -------------------------------------------------------------


def _detect_cargo_toml(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # pragma: no cover
        logger.debug(f"Failed to parse {path}: {exc}")
        return out
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        deps = data.get(section, {}) or {}
        for name, value in deps.items():
            if isinstance(value, str):
                out.append({"id": name.lower(), "version": value})
            elif isinstance(value, dict):
                out.append({"id": name.lower(), "version": value.get("version", "")})
    return out


# Public API -------------------------------------------------------------


_MANIFESTS: tuple[tuple[str, Any], ...] = (
    ("pyproject.toml", _detect_pyproject),
    ("package.json", _detect_package_json),
    ("go.mod", _detect_go_mod),
    ("Cargo.toml", _detect_cargo_toml),
)


def detect_manifests(project_path: Path) -> list[dict]:
    """Walk known manifests at ``project_path`` (top level only) and return
    a deduplicated flat list of ``{"id", "version"}`` entries.

    Multi-language projects (e.g. a Python + JS codebase with both
    pyproject.toml and package.json) keep both lists merged because
    library IDs are ecosystem-namespaced in real usage (``react`` is npm,
    ``fastapi`` is PyPI — no collision).
    """
    project_path = project_path.expanduser().resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(f"Not a directory: {project_path}")

    out: list[dict] = []
    for manifest_name, parser in _MANIFESTS:
        path = project_path / manifest_name
        if path.exists():
            out.extend(parser(path))

    # Dedupe — last writer wins on conflict.
    seen: dict[str, dict] = {}
    for entry in out:
        if not entry["id"]:
            continue
        seen[entry["id"]] = entry
    return list(seen.values())


def lock_project(db: Any, project_path: Path) -> dict:
    """Detect manifests at ``project_path``, persist the lock, return summary.

    Each detected manifest entry is matched against the libraries table by
    name (case-insensitive); when a match is found the canonical
    ``library_id`` is stored alongside the version pin so ``docs_query``
    can pivot on the lock list deterministically.
    """
    project_path = project_path.expanduser().resolve()
    detected = detect_manifests(project_path)

    enriched: list[dict] = []
    for entry in detected:
        name = entry["id"]
        version = entry.get("version", "")
        lib_row = db.get_library(name)
        lib_id = lib_row["id"] if lib_row else None
        enriched.append(
            {
                "id": lib_id or name,
                "name": name,
                "version": version,
                "indexed": lib_row is not None,
            }
        )

    # Lazy import: runtime pulls the hull provider stack, so keep it off the
    # module import path for callers that only need manifest detection.
    from wet_mcp.runtime import current_sub

    db.upsert_project_context(str(project_path), enriched, sub=current_sub())

    return {
        "project_path": str(project_path),
        "locked_libraries": enriched,
        "total": len(enriched),
        "indexed": sum(1 for e in enriched if e["indexed"]),
    }


# tomllib is stdlib since 3.11 — wet-mcp pins ==3.13.* so it is always available.
