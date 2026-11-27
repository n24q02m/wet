"""Package-level dynamic attribute resolution for patch compatibility."""

from __future__ import annotations

import sys
from typing import Any


def pkg_attr(name: str, fallback: Any) -> Any:
    """Resolve *name* on ``wet.sources.docs`` at call time if loaded.

    Preserves ``unittest.mock.patch("wet.sources.docs.<name>")`` interception
    across split submodules without circular or stale value imports.
    """
    pkg = sys.modules.get("wet.sources.docs")
    if pkg is not None and name in pkg.__dict__:
        return pkg.__dict__[name]
    return fallback
