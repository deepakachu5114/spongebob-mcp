"""The little static file server that gives every rendered site a real URL.

Two ways in:

* ``ensure_running()`` — used by the MCP server. Starts a daemon thread on first
  render, or adopts an already-running spongebob server (started by
  ``spongebob serve``) if one holds the port.
* ``serve_forever()`` — used by ``spongebob serve``, which keeps sites reachable
  after the MCP client exits.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config

MARKER_NAME = ".spongebob.json"
PORT_SCAN_LIMIT = 40

_lock = threading.Lock()
_thread: threading.Thread | None = None
_server: ThreadingHTTPServer | None = None
_port: int | None = None


class _Handler(SimpleHTTPRequestHandler):
    """Quiet, no-cache handler. No-cache matters because every incremental patch
    rewrites the HTML in place and we want a plain reload to show it."""

    server_version = "spongebob"
    sys_version = ""

    def end_headers(self) -> None:  # noqa: D102
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: D102, ANN002
        if os.environ.get("SPONGEBOB_ACCESS_LOG"):
            super().log_message(fmt, *args)


def _write_marker(port: int) -> None:
    config.ensure_dirs()
    marker = {"service": "spongebob", "port": port, "pid": os.getpid()}
    (config.sites_dir() / MARKER_NAME).write_text(json.dumps(marker) + "\n", encoding="utf-8")
    config.state_file().write_text(json.dumps(marker) + "\n", encoding="utf-8")


def _is_ours(host: str, port: int) -> bool:
    """Ask a listener on this port whether it is a spongebob server."""
    url = f"http://{host if host not in ('0.0.0.0', '::', '') else '127.0.0.1'}:{port}/{MARKER_NAME}"
    try:
        with urllib.request.urlopen(url, timeout=0.75) as response:  # noqa: S310 - loopback only
            return json.loads(response.read()).get("service") == "spongebob"
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1" if host in ("0.0.0.0", "::", "") else host, port)) == 0


def _make_server(host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(_Handler, directory=str(config.sites_dir()))
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def _bind(preferred: int | None = None) -> tuple[ThreadingHTTPServer, int]:
    """Bind the preferred port, or the next free one after it."""
    config.ensure_dirs()
    host = config.bind_host()
    start = preferred or config.preferred_port()
    last_error: OSError | None = None
    for candidate in range(start, start + PORT_SCAN_LIMIT):
        try:
            return _make_server(host, candidate), candidate
        except OSError as error:
            last_error = error
            continue
    raise RuntimeError(
        f"no free port in {start}..{start + PORT_SCAN_LIMIT - 1}"
    ) from last_error


def running_port() -> int | None:
    """Port of a spongebob server reachable right now, if any."""
    if _port is not None:
        return _port
    host = config.bind_host()
    candidates = []
    try:
        recorded = json.loads(config.state_file().read_text(encoding="utf-8"))
        candidates.append(int(recorded["port"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if config.preferred_port() not in candidates:
        candidates.append(config.preferred_port())
    for candidate in candidates:
        if _port_in_use(host, candidate) and _is_ours(host, candidate):
            return candidate
    return None


def ensure_running() -> int:
    """Return the port a spongebob server is serving on, starting one if needed."""
    global _thread, _server, _port

    with _lock:
        if _port is not None and _thread is not None and _thread.is_alive():
            return _port

        adopted = running_port()
        if adopted is not None:
            _port = adopted
            return adopted

        server, port = _bind()
        _write_marker(port)
        thread = threading.Thread(
            target=server.serve_forever, name="spongebob-http", daemon=True
        )
        thread.start()
        _server, _thread, _port = server, thread, port
        return port


def serve_forever(port: int | None = None) -> None:
    """Blocking server for ``spongebob serve``."""
    global _server, _port
    server, bound = _bind(port)
    _write_marker(bound)
    _server, _port = server, bound
    print(f"spongebob serving {config.sites_dir()} at {config.public_base_url(bound)}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()


def base_url(port: int | None = None) -> str:
    resolved = port or _port or running_port() or config.preferred_port()
    return config.public_base_url(resolved)


def site_url(slug: str, port: int | None = None) -> str:
    return f"{base_url(port)}/{slug}/"


def stop() -> None:
    """Shut down an in-process server. Used by tests."""
    global _server, _thread, _port
    with _lock:
        if _server is not None:
            _server.shutdown()
            _server.server_close()
        _server = _thread = _port = None


def site_dir_path(slug: str) -> Path:
    return config.site_dir(slug)
