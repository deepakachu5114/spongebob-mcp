"""Filesystem locations and tunables, all overridable by environment variable."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PORT = 8787
PORT_ENV = "SPONGEBOB_PORT"
DATA_ENV = "SPONGEBOB_DATA_DIR"
HOST_ENV = "SPONGEBOB_HOST"
PUBLIC_URL_ENV = "SPONGEBOB_PUBLIC_URL"


def data_dir() -> Path:
    """Root directory holding every rendered site plus the server state file."""
    override = os.environ.get(DATA_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".local" / "share" / "spongebob"


def sites_dir() -> Path:
    return data_dir() / "sites"


def state_file() -> Path:
    """Where the running static server records the port it actually bound."""
    return data_dir() / "server.json"


def site_dir(slug: str) -> Path:
    return sites_dir() / slug


def preferred_port() -> int:
    raw = os.environ.get(PORT_ENV)
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def bind_host() -> str:
    """Interface the static server listens on. Loopback unless told otherwise."""
    return os.environ.get(HOST_ENV, "127.0.0.1")


def public_base_url(port: int) -> str:
    """Base URL handed back to callers. Override when running behind a container
    port mapping or a reverse proxy."""
    override = os.environ.get(PUBLIC_URL_ENV)
    if override:
        return override.rstrip("/")
    host = bind_host()
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def ensure_dirs() -> None:
    sites_dir().mkdir(parents=True, exist_ok=True)
