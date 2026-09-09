"""Persistence for rendered sites.

``payload.json`` inside each site directory is the single source of truth. Every
incremental mutation reads it, changes it, writes it back, and re-renders — so a
site can always be rebuilt from disk and nothing lives only in memory.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import config
from .models import SitePayload, slugify

PAYLOAD_FILENAME = "payload.json"


class SiteNotFound(KeyError):
    """Raised when a slug does not correspond to a stored site."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug

    def __str__(self) -> str:  # pragma: no cover - message only
        known = ", ".join(s.slug for s in list_sites()) or "none"
        return f"no site named {self.slug!r}; known sites: {known}"


class SiteExists(FileExistsError):
    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug

    def __str__(self) -> str:  # pragma: no cover - message only
        return f"site {self.slug!r} already exists; pass overwrite=true to replace it"


@dataclass(frozen=True)
class SiteSummary:
    slug: str
    title: str
    updated_at: str
    section_count: int
    card_count: int


def safe_slug(slug: str) -> str:
    """Normalise a caller-supplied slug and refuse anything path-like."""
    if not slug or not isinstance(slug, str):
        raise ValueError("slug must be a non-empty string")
    cleaned = slugify(slug, fallback="")
    if not cleaned:
        raise ValueError(f"slug {slug!r} contains no usable characters")
    return cleaned


def payload_path(slug: str) -> Path:
    return config.site_dir(safe_slug(slug)) / PAYLOAD_FILENAME


def exists(slug: str) -> bool:
    return payload_path(slug).is_file()


def save_payload(payload: SitePayload) -> Path:
    """Write ``payload.json``. Returns the site directory."""
    directory = config.site_dir(safe_slug(payload.slug))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / PAYLOAD_FILENAME
    serialised = payload.model_dump(mode="json", exclude_none=True)
    # Write-then-rename so a crash mid-write cannot leave a truncated payload.
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(serialised, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return directory


def load_payload(slug: str) -> SitePayload:
    path = payload_path(slug)
    if not path.is_file():
        raise SiteNotFound(safe_slug(slug))
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SitePayload.model_validate(raw)


def load_raw(slug: str) -> dict:
    path = payload_path(slug)
    if not path.is_file():
        raise SiteNotFound(safe_slug(slug))
    return json.loads(path.read_text(encoding="utf-8"))


def updated_at(slug: str) -> str:
    path = payload_path(slug)
    stamp = _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.timezone.utc)
    return stamp.isoformat(timespec="seconds")


def list_sites() -> list[SiteSummary]:
    root = config.sites_dir()
    if not root.is_dir():
        return []
    summaries: list[SiteSummary] = []
    for directory in sorted(root.iterdir()):
        candidate = directory / PAYLOAD_FILENAME
        if not candidate.is_file():
            continue
        try:
            payload = SitePayload.model_validate(json.loads(candidate.read_text(encoding="utf-8")))
        except Exception:
            continue
        cards = sum(
            len(deck.cards)
            for section in payload.sections
            if section.type == "flashcards"
            for deck in section.decks
        )
        summaries.append(
            SiteSummary(
                slug=payload.slug,
                title=payload.meta.title,
                updated_at=updated_at(payload.slug),
                section_count=len(payload.sections),
                card_count=cards,
            )
        )
    return summaries


def delete_site(slug: str) -> bool:
    directory = config.site_dir(safe_slug(slug))
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True
