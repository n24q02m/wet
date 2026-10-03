"""Process-wide identity seed (E1-f): derive once, persist, reuse.

Wet's identity layer (``hull_web.fingerprint.build_identity``) needs a stable
integer seed so every strategy in the chain presents the same person across
requests AND across server restarts. Resolution order:

1. ``WET_IDENTITY_SEED`` env var (explicit pin, wins over everything);
2. ``settings.identity_seed`` when nonzero;
3. the persisted seed in ``<sub_root()>/identity.json``;
4. a fresh random seed, persisted so the next boot reuses it.

Plaintext JSON by design: the seed is a fingerprint *selector*, not a
credential — leaking it does not grant access to anything. Unlike vault
secrets it is safe to rotate by deleting the file (a new person is derived on
next start). Per-namespace file layout follows the existing ``sub_root()``
(mode-3) convention, so two namespaces never share a person.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from loguru import logger

_IDENTITY_FILE = "identity.json"


def _identity_path() -> Path:
    from wet.runtime import sub_root

    return sub_root() / _IDENTITY_FILE


def _read_persisted(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # corrupted file: derive fresh, don't wedge startup
        logger.warning(f"identity file unreadable ({exc}); deriving a fresh seed")
        return None
    seed = data.get("identity_seed") if isinstance(data, dict) else None
    if isinstance(seed, int) and seed > 0:
        return seed
    return None


def _persist(path: Path, seed: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"identity_seed": seed}, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        # Failure to persist must never break the server: log and continue
        # with the in-memory seed (identity rotates on restart instead).
        logger.warning(f"could not persist identity seed ({exc}); using in-memory seed")


def get_or_create_identity_seed() -> int:
    """Env pin → configured seed → persisted seed → fresh random (persisted)."""
    import os

    from wet.config import settings

    raw = (os.getenv("WET_IDENTITY_SEED", "") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                f"WET_IDENTITY_SEED={raw!r} is not an integer; falling through"
            )

    if settings.identity_seed > 0:
        return settings.identity_seed

    path = _identity_path()
    persisted = _read_persisted(path)
    if persisted is not None:
        return persisted

    seed = secrets.randbelow(2**31 - 1) + 1
    _persist(path, seed)
    return seed


def identity_profile_dir() -> str:
    """Per-namespace persistent-profile dir for the invisible engine tier."""
    from wet.config import settings
    from wet.runtime import sub_root

    if settings.identity_profile_dir:
        return settings.identity_profile_dir
    return str(sub_root() / "profiles")
