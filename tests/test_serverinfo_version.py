"""Regression test: serverInfo.version reports wet-mcp's own version.

FastMCP (the SDK class) does not accept a ``version=`` kwarg, so the underlying
lowlevel Server defaults ``.version`` to ``None`` and the SDK fills
``serverInfo`` with the ``mcp`` package version instead. ``server.py`` sets
``mcp._mcp_server.version`` explicitly; this test asserts it propagates to
``create_initialization_options().server_version`` and is wet-mcp's version,
not the mcp SDK's.
"""

from __future__ import annotations

import importlib
import sys
from importlib.metadata import version


def test_serverinfo_reports_wet_mcp_version() -> None:
    # ``test_server_timeout.py`` re-imports ``wet_mcp.server`` under heavy
    # mocking (FastMCP -> MagicMock) and can leave a mocked module behind in
    # ``sys.modules``. Force a clean re-import so we exercise the real FastMCP
    # and the real lowlevel Server, not a MagicMock.
    sys.modules.pop("wet_mcp.server", None)
    server = importlib.import_module("wet_mcp.server")

    wet_version = version("wet-mcp")
    server_version = (
        server.mcp._mcp_server.create_initialization_options().server_version
    )

    assert server_version == wet_version

    mcp_sdk_version = version("mcp")
    assert server_version != mcp_sdk_version, (
        "serverInfo.version must report wet-mcp's version, not the mcp SDK "
        f"version ({mcp_sdk_version})."
    )
