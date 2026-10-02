"""Test that SearXNG settings get unique secret keys (via web-core)."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from hull_web.search.runner import _get_settings_path


def test_secret_key_is_random_and_hex():
    """Verify that _get_settings_path generates a unique random secret key."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("hull_web.search.runner._CONFIG_DIR", Path(tmp)):
            settings_path = _get_settings_path(9090)
            content = settings_path.read_text()

    # Verify port replacement
    assert "port: 9090" in content

    # Verify secret key is present and random
    for line in content.splitlines():
        if "secret_key:" in line:
            secret = line.split(":", 1)[1].strip().strip('"')
            # 32 bytes hex = 64 chars
            assert len(secret) == 64
            # Verify it is hex
            int(secret, 16)
            break
    else:
        raise AssertionError("secret_key not found in settings")


def test_secret_key_unique_per_call():
    """Each call should generate a different secret key."""
    secrets = []
    with tempfile.TemporaryDirectory() as tmp:
        with patch("hull_web.search.runner._CONFIG_DIR", Path(tmp)):
            for _ in range(3):
                settings_path = _get_settings_path(9090)
                content = settings_path.read_text()
                for line in content.splitlines():
                    if "secret_key:" in line:
                        secrets.append(line.split(":", 1)[1].strip().strip('"'))
                        break

    assert len(set(secrets)) == 3, "All secret keys should be unique"
