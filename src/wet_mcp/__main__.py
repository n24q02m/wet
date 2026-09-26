"""``python -m wet_mcp`` entry point.

- NO args, or ``--serve`` (optionally with ``--host H`` / ``--port P``):
  run the BLOCKING wet HTTP server in-process — ``wet_mcp.server``
  ``run_server_blocking(host, port)`` when that lane's entry is present,
  falling back to that module's ``main()``.
- anything else: dispatch through the ``wet`` CLI control plane
  (:func:`wet_mcp.cli.main`).
"""

from __future__ import annotations

import sys


def _serve(argv: list[str]) -> int:
    import os

    import wet_mcp.server as server_mod

    host: str | None = os.environ.get("WET_HOST") or None
    port_arg = os.environ.get("WET_PORT")
    port: int | None = int(port_arg) if port_arg else None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
            i += 2
        elif token == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])
            i += 2
        else:
            i += 1

    entry = getattr(server_mod, "run_server_blocking", None)
    if entry is not None:
        entry(host=host, port=port)
        return 0
    # Defensive fallback: the server module's own entry (may default to a
    # different transport; `wet server start --foreground` is the supported
    # path for the blocking HTTP server).
    server_mod.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "--serve":
        return _serve(argv[1:] if argv else [])
    from wet_mcp.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
