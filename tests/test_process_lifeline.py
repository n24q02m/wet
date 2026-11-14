"""Live-server teardown must not leak processes, however the test process ends.

Each aborted live run (pytest-timeout ``os._exit`` on Windows, a killed run)
used to leave a ``wet.server`` launcher + interpreter pair alive; 70 of them
starved a later run of RAM. These tests drive ``live_http``'s supervisor with
a stand-in server that starts a grandchild, so they run in the default suite
on every OS without the real server.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psutil
from live_http import spawn_supervised
from process_lifeline import stop_supervised

TESTS_DIR = Path(__file__).parent

# Stand-in server: starts a grandchild, publishes both pids, then idles.
_TREE = textwrap.dedent(
    """
    import os, subprocess, sys, time
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    tmp = sys.argv[1] + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(f"{os.getpid()} {grandchild.pid}")
    os.replace(tmp, sys.argv[1])
    time.sleep(600)
    """
)

# Owner that dies without teardown, the way a timed-out or killed run does.
_ABRUPT_OWNER = textwrap.dedent(
    """
    import os, sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from live_http import spawn_supervised
    tree, pid_file, log = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    proc = spawn_supervised([sys.executable, "-c", tree, str(pid_file)], dict(os.environ), log)
    deadline = time.monotonic() + 20
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    print(proc.pid, flush=True)
    os._exit(1)
    """
)


def _wait_for_pids(pid_file: Path, timeout: float = 20.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while not pid_file.exists():
        assert time.monotonic() < deadline, f"stand-in server never wrote {pid_file}"
        time.sleep(0.05)
    return [int(pid) for pid in pid_file.read_text().split()]


def _processes(pids: list[int]) -> list[psutil.Process]:
    procs = []
    for pid in pids:
        try:
            procs.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            continue  # already gone counts as stopped
    return procs


def test_teardown_stops_the_whole_server_tree(tmp_path: Path) -> None:
    pid_file = tmp_path / "pids"
    proc = spawn_supervised(
        [sys.executable, "-c", _TREE, str(pid_file)],
        dict(os.environ),
        tmp_path / "server.log",
    )
    server_pid, grandchild_pid = _wait_for_pids(pid_file)
    tree = [
        psutil.Process(proc.pid),
        *psutil.Process(proc.pid).children(recursive=True),
    ]
    assert {server_pid, grandchild_pid} <= {p.pid for p in tree}

    stop_supervised(proc)

    _, alive = psutil.wait_procs(tree, timeout=5)
    assert alive == [], f"leaked after teardown: {[p.pid for p in alive]}"


def test_server_tree_dies_with_an_owner_that_skips_teardown(tmp_path: Path) -> None:
    pid_file = tmp_path / "pids"
    owner = subprocess.run(
        [
            sys.executable,
            "-c",
            _ABRUPT_OWNER,
            str(TESTS_DIR),
            _TREE,
            str(pid_file),
            str(tmp_path / "server.log"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert owner.returncode == 1, owner.stderr
    supervisor_pid = int(owner.stdout.split()[0])
    server_pid, grandchild_pid = _wait_for_pids(pid_file)

    tree = _processes([supervisor_pid, server_pid, grandchild_pid])
    _, alive = psutil.wait_procs(tree, timeout=20)
    assert alive == [], f"leaked after owner died: {[p.pid for p in alive]}"
