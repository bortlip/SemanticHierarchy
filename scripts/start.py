"""Start the local Semantic Hierarchy server and open the browser.

Standard library only. This launcher does not read, display, or store API keys.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def port_is_available(port: int) -> bool:
    """Do not open a browser to an unrelated service on an occupied port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def wait_for_server(process: subprocess.Popen, url: str, timeout: float = 20.0) -> None:
    """Only open the browser after our own child server is responding."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The web server exited during startup.")
        try:
            with urllib.request.urlopen(url + "/api/config", timeout=0.6) as reply:
                data = json.load(reply)
                if reply.status == 200 and isinstance(data.get("models"), list):
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("The server did not become ready within 20 seconds.")


def stop_child(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch Semantic Hierarchy locally.")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("Dependencies are missing. Install requirements into .venv first.", file=sys.stderr)
        return 1

    if not port_is_available(args.port):
        print(
            f"Port {args.port} is in use. Close the other server or run "
            f"scripts\\start.cmd --port 8765 instead.",
            file=sys.stderr,
        )
        return 2

    url = f"http://{HOST}:{args.port}"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "web_app:app",
        "--host",
        HOST,
        "--port",
        str(args.port),
    ]
    print(f"Starting Semantic Hierarchy at {url}", flush=True)
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        wait_for_server(process, url)
        if not args.no_browser:
            print("Opening your default browser...", flush=True)
            if not webbrowser.open(url):
                print(f"Browser did not open automatically. Navigate to {url}", flush=True)
        print(f"Ready: {url}  (press Ctrl+C here to stop the server)", flush=True)
        process.wait()
        return 0 if process.returncode == 0 else 1
    except KeyboardInterrupt:
        print("\nStopping server...", flush=True)
        return 0
    except RuntimeError as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1
    finally:
        stop_child(process)


if __name__ == "__main__":
    raise SystemExit(main())
