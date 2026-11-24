"""Project manifest + lockfile detection, docs status & audit (WET-10, WET-26, WET-41).

Walks a project root and detects supported manifests (``pyproject.toml``,
``package.json``, ``go.mod``, ``Cargo.toml``, ``Gemfile``, ``composer.json``)
and all 12 ecosystem lockfiles (``uv.lock``, ``poetry.lock``, ``pdm.lock``,
``requirements.txt``, ``package-lock.json``, ``pnpm-lock.yaml``, ``yarn.lock``,
``bun.lock``, ``Cargo.lock``, ``go.sum``, ``Gemfile.lock``, ``composer.lock``).
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
                short = name.removeprefix("github.com/")
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


# 12 ecosystem lockfiles --------------------------------------------------


def _detect_uv_or_toml_lock(path: Path) -> list[dict]:
    """Parse ``uv.lock``, ``poetry.lock``, ``pdm.lock``, or ``Cargo.lock``."""
    out: list[dict] = []
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # pragma: no cover
        logger.debug(f"Failed to parse {path}: {exc}")
        return out
    for pkg in data.get("package", []) or []:
        if not isinstance(pkg, dict):
            continue
        name = str(pkg.get("name") or "").strip().lower()
        version = str(pkg.get("version") or "").strip()
        if name and version:
            out.append({"id": name, "version": version})
    return out


def _detect_requirements_txt(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return out
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "--")):
            continue
        name, version = _parse_pep508(line)
        if name:
            out.append({"id": name.lower(), "version": version})
    return out


def _detect_package_lock_json(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return out
    packages = data.get("packages") or {}
    if isinstance(packages, dict):
        for pkg_path, info in packages.items():
            if not pkg_path or not isinstance(info, dict):
                continue
            name = str(info.get("name") or "")
            if not name and "node_modules/" in pkg_path:
                name = pkg_path.rsplit("node_modules/", 1)[-1]
            version = str(info.get("version") or "")
            if name and not name.startswith("@types/"):
                out.append({"id": name.lower(), "version": version})
    deps = data.get("dependencies") or {}
    if isinstance(deps, dict):
        for name, info in deps.items():
            if isinstance(info, dict) and not name.startswith("@types/"):
                out.append(
                    {"id": name.lower(), "version": str(info.get("version") or "")}
                )
    return out


_PNPM_PKG_KEY_RE = re.compile(r"^['\"]?/?(@?[^@/'\"(]+)@([^('\":\s]+)")


def _detect_pnpm_lock_yaml(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return out
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _PNPM_PKG_KEY_RE.match(stripped)
        if m:
            name, version = m.group(1).lower(), m.group(2)
            if not name.startswith("@types/"):
                out.append({"id": name, "version": version})
        elif stripped.startswith("specifier:") or stripped.startswith("version:"):
            continue
    return out


_YARN_HEADER_RE = re.compile(r'^"?(@?[^@"\s]+)@[^":\n]+[":]')
_YARN_VERSION_RE = re.compile(r'^\s+version(?:\s+|:\s*)"?([^\s"]+)"?')


def _detect_yarn_lock(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return out
    current_name = ""
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            m = _YARN_HEADER_RE.match(raw.strip())
            current_name = m.group(1).lower() if m else ""
            continue
        if current_name:
            vm = _YARN_VERSION_RE.match(raw)
            if vm:
                if not current_name.startswith("@types/"):
                    out.append({"id": current_name, "version": vm.group(1)})
                current_name = ""
    return out


def _detect_bun_lock(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8")
        # Strip trailing commas (JSONC in bun.lock)
        cleaned = re.sub(r",(\s*[}\]])", r"\1", raw)
        data = json.loads(cleaned)
    except Exception:  # pragma: no cover
        return out
    packages = data.get("packages") or {}
    if isinstance(packages, dict):
        for name, entry in packages.items():
            version = ""
            if isinstance(entry, list) and entry and isinstance(entry[0], str):
                pkg_spec = entry[0]
                if "@" in pkg_spec.lstrip("@"):
                    version = pkg_spec.rsplit("@", 1)[-1]
            elif isinstance(entry, dict):
                version = str(entry.get("version") or "")
            if name and not name.startswith("@types/"):
                out.append({"id": name.lower(), "version": version})
    return out


_GO_SUM_LINE_RE = re.compile(r"^(\S+)\s+(v[^\s/]+)(?:/go\.mod)?\s+")


def _detect_go_sum(path: Path) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return out
    for raw in text.splitlines():
        m = _GO_SUM_LINE_RE.match(raw.strip())
        if not m:
            continue
        name = m.group(1).removeprefix("github.com/").lower()
        version = m.group(2)
        if name not in seen:
            seen.add(name)
            out.append({"id": name, "version": version})
    return out


_GEMFILE_SPEC_RE = re.compile(r"^\s{4}([A-Za-z0-9_.\-]+)\s+\(([^)]+)\)")


def _detect_gemfile_lock(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return out
    for raw in text.splitlines():
        m = _GEMFILE_SPEC_RE.match(raw)
        if m:
            out.append({"id": m.group(1).lower(), "version": m.group(2)})
    return out


def _detect_composer_lock(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return out
    for section in ("packages", "packages-dev"):
        for pkg in data.get(section, []) or []:
            if not isinstance(pkg, dict):
                continue
            name = str(pkg.get("name") or "").strip().lower()
            version = str(pkg.get("version") or "").strip()
            if name:
                out.append({"id": name, "version": version})
    return out


# Public API -------------------------------------------------------------


_MANIFESTS: tuple[tuple[str, Any], ...] = (
    ("pyproject.toml", _detect_pyproject),
    ("package.json", _detect_package_json),
    ("go.mod", _detect_go_mod),
    ("Cargo.toml", _detect_cargo_toml),
    # 12 lockfiles: parsed after manifests so pinned lock versions enrich constraints.
    ("requirements.txt", _detect_requirements_txt),
    ("uv.lock", _detect_uv_or_toml_lock),
    ("poetry.lock", _detect_uv_or_toml_lock),
    ("pdm.lock", _detect_uv_or_toml_lock),
    ("package-lock.json", _detect_package_lock_json),
    ("pnpm-lock.yaml", _detect_pnpm_lock_yaml),
    ("yarn.lock", _detect_yarn_lock),
    ("bun.lock", _detect_bun_lock),
    ("Cargo.lock", _detect_uv_or_toml_lock),
    ("go.sum", _detect_go_sum),
    ("Gemfile.lock", _detect_gemfile_lock),
    ("composer.lock", _detect_composer_lock),
)

SUPPORTED_LOCKFILES: tuple[str, ...] = (
    "uv.lock",
    "poetry.lock",
    "pdm.lock",
    "requirements.txt",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
)


def docs_status(db: Any) -> dict[str, Any]:
    """Return local docs index summary: libraries, versions, chunks, and health."""
    return db.docs_status_summary()


def docs_audit(db: Any, project_path: Path, *, sub: str = "default") -> dict[str, Any]:
    """Audit a project's detected dependencies against the local docs database."""
    project_path = project_path.expanduser().resolve()
    detected = detect_manifests(project_path)
    context = db.get_project_context(str(project_path), sub=sub)
    locked_ids = {
        str(item.get("name") or item.get("id") or "").lower()
        for item in (context or {}).get("locked_libraries", [])
    }

    indexed: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    for entry in detected:
        name = entry["id"]
        version = entry.get("version", "")
        lib_row = db.get_library(name)
        item = {
            "id": lib_row["id"] if lib_row else name,
            "name": name,
            "version": version,
            "locked": name in locked_ids,
        }
        if lib_row is None:
            missing.append({**item, "status": "missing"})
            continue
        versions = (
            db.list_versions(lib_row["id"]) if hasattr(db, "list_versions") else []
        )
        has_indexed_version = any(v.get("status") == "indexed" for v in versions) or (
            hasattr(db, "get_best_version")
            and db.get_best_version(lib_row["id"]) is not None
        )
        if has_indexed_version or lib_row.get("last_indexed_at"):
            indexed.append({**item, "status": "indexed"})
        else:
            stale.append({**item, "status": "unindexed"})

    return {
        "project_path": str(project_path),
        "total_dependencies": len(detected),
        "indexed_count": len(indexed),
        "missing_count": len(missing),
        "stale_count": len(stale),
        "indexed": indexed,
        "missing": missing,
        "stale": stale,
    }


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
    from wet.runtime import current_sub

    db.upsert_project_context(str(project_path), enriched, sub=current_sub())

    return {
        "project_path": str(project_path),
        "locked_libraries": enriched,
        "total": len(enriched),
        "indexed": sum(1 for e in enriched if e["indexed"]),
    }


# tomllib is stdlib since 3.11 — wet pins ==3.13.* so it is always available.
