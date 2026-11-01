"""Plugin hook manifest: every command in hooks/hooks.json must resolve to a real script."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"


def _commands() -> list[str]:
    manifest = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return [
        hook["command"]
        for groups in manifest["hooks"].values()
        for group in groups
        for hook in group["hooks"]
        if hook["type"] == "command"
    ]


def test_hooks_manifest_lists_both_shipped_scripts():
    commands = _commands()
    shipped = sorted(p.name for p in (ROOT / "hooks").glob("*.sh"))
    assert shipped
    assert sorted(Path(c).name for c in commands) == shipped


def test_every_hook_command_points_at_an_existing_script():
    for command in _commands():
        assert command.startswith(f"{PLUGIN_ROOT_VAR}/hooks/")
        script = ROOT / command.removeprefix(f"{PLUGIN_ROOT_VAR}/")
        assert script.is_file(), command
