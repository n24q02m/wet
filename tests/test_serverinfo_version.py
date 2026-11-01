"""Regression test: serverInfo.version reports wet's own version.

``server.py`` passes ``version=`` to ``MCPServer``; this test asserts the
server reports wet's version, not the mcp SDK's.
"""

from __future__ import annotations

import importlib
import sys
from importlib.metadata import version


def test_serverinfo_reports_wet_version() -> None:
    # ``test_server_timeout.py`` re-imports ``wet.server`` under heavy
    # mocking (MCPServer -> MagicMock) and can leave a mocked module behind in
    # ``sys.modules``. Force a clean re-import so we exercise the real
    # MCPServer, not a MagicMock.
    sys.modules.pop("wet.server", None)
    server = importlib.import_module("wet.server")

    try:
        wet_version = version("n24q02m-wet")
    except Exception:
        wet_version = version("wet-mcp")
    server_version = server.mcp.version

    assert server_version == wet_version

    mcp_sdk_version = version("mcp")
    assert server_version != mcp_sdk_version, (
        "serverInfo.version must report wet's version, not the mcp SDK "
        f"version ({mcp_sdk_version})."
    )
