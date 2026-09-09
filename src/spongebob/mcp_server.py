"""The MCP surface.

Two families of tools:

* one-shot rendering — ``get_payload_schema`` then ``render_site``
* incremental mutation — everything else, so an agent can grow a site over
  several turns without resending the whole payload

Every mutating tool re-renders the site and returns the same URL, so the caller
can always hand that link straight to the user.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from . import __version__, config, patch, serve, store
from .models import SECTION_TYPES, SitePayload
from .render import render_site as _render_files
from .render import render_site_index

INSTRUCTIONS = """\
spongebob renders a JSON description of a learning site into a served,
single-page website and returns its URL.

Typical flow:
  1. get_payload_schema()  — read the schema and the worked example
  2. render_site(payload)  — returns {"url": ...}; hand that URL to the user
  3. add_flashcards / add_resources / update_section / ... — enrich later
     without resending the payload

Canonical section order for an onboarding site:
  overview → resources → first-task (markdown) → how-it-works (markdown)
  → flashcards → quiz

Stick to this flow. Do not invent new section types or add arbitrary extra
sections — the six named types cover all onboarding needs.

Section types: overview, resources (YouTube/blogs/courses — YouTube URLs embed
automatically), flashcards (SM-2 spaced repetition), quiz (mcq/multi/true_false),
markdown (prose + code blocks), custom (freeform blocks).
"""

server = MCPServer(
    name="spongebob",
    title="spongebob",
    version=__version__,
    instructions=INSTRUCTIONS,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _url(slug: str) -> str:
    """Make sure a server is up, then build the site URL."""
    return serve.site_url(slug, serve.ensure_running())


def _result(payload: dict) -> dict:
    payload["url"] = _url(payload["slug"])
    return payload


def _summary(slug: str) -> dict:
    stored = store.load_payload(slug)
    return {
        "slug": stored.slug,
        "title": stored.meta.title,
        "url": _url(stored.slug),
        "sections": [
            {"id": s.id, "type": s.type, "title": s.title, "page": s.filename if s.page else None}
            for s in stored.sections
        ],
        "decks": [
            {"id": deck.id, "name": deck.name, "cards": len(deck.cards)}
            for s in stored.sections
            if s.type == "flashcards"
            for deck in s.decks
        ],
        "learning_path": [step.title for step in stored.learning_path],
        "updated_at": store.updated_at(stored.slug),
    }


def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Surface anticipated failures to the caller.

    MCPServer only forwards the message of a ``ToolError``; anything else
    reaches the model as a bare "Error executing tool <name>". Our failures
    carry the guidance the calling agent needs to recover — which deck ids
    exist, which tool to use instead — so they must arrive as ``ToolError``.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except (patch.PatchError, store.SiteNotFound, store.SiteExists, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def get_payload_schema(include_example: bool = True) -> dict[str, Any]:
    """Return the JSON Schema for a site payload, plus a worked example.

    Call this before render_site the first time. The schema is permissive:
    unknown keys are preserved and shown on the page, and an unknown section
    `type` degrades to a generic custom section rather than failing.
    """
    result: dict[str, Any] = {
        "json_schema": SitePayload.model_json_schema(),
        "section_types": list(SECTION_TYPES),
        "notes": [
            "meta.slug decides the URL; it is derived from meta.title when omitted.",
            "Canonical section order: overview → resources → first-task (markdown) "
            "→ how-it-works (markdown) → flashcards → quiz. Stick to this flow.",
            "learning_path[].target must be a section id (e.g. 'overview'). "
            "The site is single-page; all sections are anchors on index.html.",
            "Resource kinds: youtube, blog, course, docs, book, paper, repo, tool, other. "
            "Any YouTube URL (youtu.be, youtube.com/watch, etc.) becomes a privacy-mode embed automatically — "
            "set kind='youtube' or just use the URL and it is detected.",
            "Quiz: use mcq, multi, or true_false. Do NOT use 'short' — open-ended answers are not supported in the UI.",
            "Flashcard decks: split by theme (core / operations / pitfalls). "
            "Cards must have a verifiable answer — omit cards where you are unsure.",
            "Markdown is supported in most text fields. Raw HTML is stripped.",
        ],
    }
    if include_example:
        result["example"] = _EXAMPLE
    return result


@server.tool()
@_guard
def list_sites() -> dict[str, Any]:
    """List every site rendered on this machine, with its URL."""
    port = serve.ensure_running()
    return {
        "index_url": f"{serve.base_url(port)}/",
        "sites": [
            {
                "slug": site.slug,
                "title": site.title,
                "url": serve.site_url(site.slug, port),
                "sections": site.section_count,
                "flashcards": site.card_count,
                "updated_at": site.updated_at,
            }
            for site in store.list_sites()
        ],
    }


@server.tool()
@_guard
def get_site(slug: str, include_payload: bool = False) -> dict[str, Any]:
    """Inspect a rendered site: its sections, decks and learning path.

    Set include_payload to get the full stored JSON back — useful when you want
    to reason about existing content before patching it.
    """
    summary = _summary(slug)
    if include_payload:
        summary["payload"] = store.load_raw(slug)
    return summary


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def render_site(
    payload: Annotated[SitePayload, Field(description="The complete site description")],
    overwrite: Annotated[bool, Field(description="Replace an existing site with the same slug")] = True,
) -> dict[str, Any]:
    """Render a full site and return its URL.

    Use this once per site. To change a site afterwards, prefer the add_* and
    update_* tools — they patch the stored payload in place, so you do not have
    to resend content that has not changed.
    """
    slug = store.safe_slug(payload.slug)
    if store.exists(slug) and not overwrite:
        raise ValueError(
            f"site {slug!r} already exists. Pass overwrite=true to replace it, "
            "or use the add_*/update_* tools to patch it."
        )
    result = _render_files(payload)
    return {
        "slug": result.slug,
        "url": _url(result.slug),
        "pages": result.pages,
        "warnings": result.warnings,
    }


@server.tool()
@_guard
def delete_site(slug: str) -> dict[str, Any]:
    """Delete a rendered site and everything under it."""
    removed = store.delete_site(slug)
    render_site_index()
    return {"slug": store.safe_slug(slug), "deleted": removed}


# --------------------------------------------------------------------------- #
# Flashcards  (the "flashcards-mcp" surface from the design sketch)
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def add_flashcard_deck(
    slug: str,
    deck: Annotated[dict[str, Any], Field(description='{"id","name","description","tags","cards":[{"front","back","hint","code","code_language"}]}')],
    section_id: str | None = None,
) -> dict[str, Any]:
    """Add a new flashcard deck to a site.

    Creates a flashcards section if the site does not have one yet. Cards are
    reviewed with an SM-2 spaced-repetition schedule in the browser.
    """
    return _result(patch.add_flashcard_deck(slug, deck, section_id))


@server.tool()
@_guard
def add_flashcards(
    slug: str,
    deck_id: str,
    cards: Annotated[list[dict[str, Any]], Field(description='[{"front","back","hint","code","code_language"}]')],
) -> dict[str, Any]:
    """Append cards to an existing deck. Markdown works in front and back."""
    return _result(patch.add_flashcards(slug, deck_id, cards))


@server.tool()
@_guard
def remove_flashcard_deck(slug: str, deck_id: str) -> dict[str, Any]:
    """Delete a flashcard deck from a site."""
    return _result(patch.remove_flashcard_deck(slug, deck_id))


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def add_resources(
    slug: str,
    items: Annotated[list[dict[str, Any]], Field(description='[{"title","url","description","kind","source","author","duration","level"}]')],
    group_label: str | None = None,
    kind: str | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    """Add prerequisite resources — YouTube videos, blog posts, courses, docs.

    Items are merged into the group whose label matches group_label, or a new
    group is created. YouTube URLs become embedded players. Mark internal wiki
    links with source="internal" so they are visually distinguished.
    """
    return _result(patch.add_resources(slug, items, group_label, kind, section_id))


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def add_section(
    slug: str,
    section: Annotated[dict[str, Any], Field(description="A section object; see get_payload_schema")],
    position: Annotated[int | None, Field(description="0-based insert position; appended when omitted")] = None,
) -> dict[str, Any]:
    """Add a section to a site, creating its own page.

    An unknown `type` is rendered as a generic custom section built from its
    `blocks`, so you can add kinds of content the schema does not name yet.
    """
    return _result(patch.add_section(slug, section, position))


@server.tool()
@_guard
def update_section(
    slug: str,
    section_id: str,
    patch_fields: Annotated[dict[str, Any], Field(description="Fields to merge into the section (shallow merge)")],
) -> dict[str, Any]:
    """Shallow-merge fields into an existing section.

    Whole list fields are replaced, not appended — to add to a list, prefer
    add_flashcards or add_resources.
    """
    return _result(patch.update_section(slug, section_id, patch_fields))


@server.tool()
@_guard
def remove_section(slug: str, section_id: str) -> dict[str, Any]:
    """Remove a section and delete its page."""
    return _result(patch.remove_section(slug, section_id))


@server.tool()
@_guard
def reorder_sections(slug: str, section_ids: list[str]) -> dict[str, Any]:
    """Reorder sections. Ids you leave out keep their relative order at the end."""
    return _result(patch.reorder_sections(slug, section_ids))


# --------------------------------------------------------------------------- #
# Learning path, meta, theme
# --------------------------------------------------------------------------- #


@server.tool()
@_guard
def add_learning_path_step(
    slug: str,
    step: Annotated[dict[str, Any], Field(description='{"title","summary","target","est_minutes"}')],
    position: int | None = None,
) -> dict[str, Any]:
    """Add a numbered step to the learning path on the landing page.

    `target` may be a section id, a page filename, an anchor or a full URL.
    """
    return _result(patch.add_learning_path_step(slug, step, position))


@server.tool()
@_guard
def set_learning_path(slug: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the whole learning path."""
    return _result(patch.set_learning_path(slug, steps))


@server.tool()
@_guard
def update_meta(
    slug: str,
    patch_fields: Annotated[dict[str, Any], Field(description='{"title","subtitle","summary","repository","repository_url","website_url","setup_file","setup_command","tags"}')],
) -> dict[str, Any]:
    """Update the hero: title, subtitle, summary, repo links, setup command."""
    return _result(patch.update_meta(slug, patch_fields))


@server.tool()
@_guard
def set_theme(
    slug: str,
    theme: Annotated[dict[str, Any], Field(description='{"accent":"#22d3ee","accent_soft":"#6366f1","dark_default":true}')],
) -> dict[str, Any]:
    """Change the site's accent colours and default light/dark mode."""
    return _result(patch.set_theme(slug, theme))


# --------------------------------------------------------------------------- #
# Example payload, loaded from the packaged example when available
# --------------------------------------------------------------------------- #


def _load_example() -> dict[str, Any]:
    from pathlib import Path

    for candidate in (
        Path(__file__).parent / "example.json",
        Path(__file__).resolve().parents[2] / "examples" / "kuya.json",
    ):
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return {
        "meta": {"title": "Example", "repository": "acme/example"},
        "learning_path": [{"title": "Overview", "target": "overview"}],
        "sections": [{"type": "overview", "title": "Overview", "business_pov": "Why it exists."}],
    }


_EXAMPLE = _load_example()


def run_stdio() -> None:
    """Entry point used by ``spongebob mcp``."""
    config.ensure_dirs()
    server.run("stdio")
