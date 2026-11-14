"""Bind a spawned server's whole process tree to the test process that owns it.

Run as ``python process_lifeline.py <argv...>``: it starts ``argv`` and blocks
reading its own stdin, a pipe whose write end only the owning test process
holds. EOF arrives when the owner closes the pipe (normal teardown) *and* when
the owner dies without running any ``finally`` -- pytest-timeout ends a run
with ``os._exit`` on Windows, and an aborted run is killed outright. On EOF
the supervisor stops the server and every descendant, then exits.

A plain ``proc.terminate()`` from the test is not enough: on Windows
``sys.executable`` in a venv is a launcher whose child interpreter serves
HTTP, and nothing at all runs when the test process is killed, so each
aborted run used to leave a live server behind.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from contextlib import suppress

import psutil

STOP_TIMEOUT = 10.0


def supervised_argv(argv: list[str]) -> list[str]:
    """Wrap ``argv`` in the supervisor; spawn it with ``stdin=subprocess.PIPE``."""
    return [sys.executable, __file__, *argv]


def stop_supervised(
    proc: subprocess.Popen[bytes], timeout: float = STOP_TIMEOUT
) -> None:
    """Cut the lifeline, reap the supervisor, and fail loudly on survivors."""
    if proc.stdin is not None and not proc.stdin.closed:
        with suppress(OSError):
            proc.stdin.close()
    try:
        proc.wait(timeout=timeout * 2)
    except subprocess.TimeoutExpired:
        alive = stop_tree(proc.pid, timeout)
        proc.wait(timeout=timeout)
        if alive:
            raise RuntimeError(
                f"server processes survived teardown: {[p.pid for p in alive]}"
            ) from None


def stop_tree(pid: int, timeout: float = STOP_TIMEOUT) -> list[psutil.Process]:
    """Terminate ``pid`` and all its descendants; return any still alive."""
    try:
        root = psutil.Process(pid)
        tree = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []
    for proc in tree:
        with suppress(psutil.NoSuchProcess):
            proc.terminate()
    _, alive = psutil.wait_procs(tree, timeout=timeout)
    for proc in alive:
        with suppress(psutil.NoSuchProcess):
            proc.kill()
    _, alive = psutil.wait_procs(alive, timeout=timeout)
    return alive


def main(argv: list[str]) -> int:
    server = subprocess.Popen(argv, stdin=subprocess.DEVNULL)  # nosec B603 - test-owned argv
    cut = threading.Event()
    watcher = threading.Thread(
        target=_watch_lifeline, args=(server.pid, cut), daemon=True
    )
    watcher.start()
    code = server.wait()
    if cut.is_set():
        # The server died because the lifeline was cut: let the watcher finish
        # stopping its descendants before this process exits.
        watcher.join()
    return code


def _watch_lifeline(server_pid: int, cut: threading.Event) -> None:
    sys.stdin.buffer.read()
    cut.set()
    stop_tree(server_pid)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
