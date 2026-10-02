"""Test MCP server stdio protocol.

Starts the MCP server and sends initialize + tools/list requests
via JSON-RPC over newline-delimited JSON (NDJSON) stdio transport.
"""

import json
import subprocess
import sys
import threading
import time


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "wet_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def send_message(msg: dict) -> None:
        line = json.dumps(msg)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    def read_message(timeout: float = 15.0) -> dict | None:
        result: list[dict | None] = [None]
        error: list[str | None] = [None]

        def _read():
            try:
                line = proc.stdout.readline()
                if line:
                    result[0] = json.loads(line.strip())
            except Exception as e:
                error[0] = str(e)

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            return None
        if error[0]:
            raise RuntimeError(error[0])
        return result[0]

    def drain_stderr() -> str:
        lines = []

        def _read():
            try:
                while True:
                    line = proc.stderr.readline()
                    if not line:
                        break
                    lines.append(line.strip())
            except Exception:
                pass

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=2)
        return "\n".join(lines)

    try:
        print("[0] Waiting for server to start...")
        time.sleep(3)

        if proc.poll() is not None:
            stderr = proc.stderr.read()
            print(f"Server exited with code {proc.returncode}")
            print(f"Stderr: {stderr[:500]}")
            return 1

        # Step 1: Initialize
        print("[1] Sending initialize (NDJSON)...")
        send_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )

        resp = read_message(timeout=10)
        if resp is None:
            print("    NDJSON: no response. Checking server logs...")
            stderr_out = drain_stderr()
            if stderr_out:
                for line in stderr_out.split("\n")[:5]:
                    print(f"    LOG: {line}")
            print("    FAIL: Server did not respond to initialize")
            return 1

        server_info = resp.get("result", {}).get("serverInfo", {})
        print(
            f"    Server: {server_info.get('name', '?')} v{server_info.get('version', '?')}"
        )
        caps = resp.get("result", {}).get("capabilities", {})
        print(f"    Capabilities: {list(caps.keys())}")

        # Step 2: Initialized notification
        send_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(1)

        # Step 3: List tools
        print("\n[2] Sending tools/list...")
        send_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        resp = read_message(timeout=10)
        if resp is None:
            print("    FAIL: No response for tools/list")
            return 1

        tools = resp.get("result", {}).get("tools", [])
        print(f"    Tools: {len(tools)}")
        for t in tools:
            print(f"      - {t['name']}: {t.get('description', '')[:60]}")

        print("\n[3] PASSED!")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
