"""Incremental edits to an already-rendered site.

Each function loads ``payload.json``, changes it, re-renders every page, and
returns the site URL. That keeps the JSON on disk authoritative and means the
agent never has to resend a whole payload to add three flashcards.
"""

from __future__ import annotations

from typing import Any, Callable

from . import config, serve, store
from .models import Deck, Flashcard, LearningPathStep, Resource, ResourceGroup, SitePayload, Theme, slugify
from .render import render_site


class PatchError(ValueError):
    """A mutation that cannot be applied — bad section id, unknown deck, etc."""


def _coerce_section(raw: dict) -> tuple[Any, list[str]]:
    """Validate one section by round-tripping it through a throwaway payload,
    so alias handling and unknown-type fallback behave exactly as on render."""
    shell = SitePayload.model_validate({"meta": {"title": "scratch"}, "sections": [raw]})
    return shell.sections[0], list(shell.warnings)


def _apply(slug: str, mutate: Callable[[SitePayload], list[str]]) -> dict:
    payload = store.load_payload(slug)
    extra_warnings = mutate(payload) or []

    # Re-validate so ids, aliases and answer normalisation are reapplied to
    # anything that was just inserted.
    payload = SitePayload.model_validate(payload.model_dump(mode="json", exclude_none=True))
    payload.warnings.extend(extra_warnings)

    result = render_site(payload)
    return {
        "slug": result.slug,
        "url": serve.site_url(result.slug),
        "pages": result.pages,
        "warnings": result.warnings,
    }


def _require_section(payload: SitePayload, section_id: str | None, section_type: str, *, title: str):
    """Find the named section, or the first of the right type, or create one."""
    if section_id:
        section = payload.section_by_id(section_id)
        if section is None:
            raise PatchError(
                f"no section with id {slugify(section_id)!r}; "
                f"existing ids: {', '.join(s.id for s in payload.sections) or 'none'}"
            )
        if section.type != section_type:
            raise PatchError(f"section {section.id!r} is a {section.type!r} section, not {section_type!r}")
        return section, False

    existing = payload.first_section_of_type(section_type)
    if existing is not None:
        return existing, False

    created, _ = _coerce_section({"type": section_type, "title": title})
    payload.sections.append(created)
    return created, True


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def add_section(slug: str, section: dict, position: int | None = None) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        parsed, warnings = _coerce_section(section)
        if payload.section_by_id(parsed.id) is not None:
            raise PatchError(f"a section with id {parsed.id!r} already exists; use update_section instead")
        index = len(payload.sections) if position is None else max(0, min(position, len(payload.sections)))
        payload.sections.insert(index, parsed)
        return warnings

    return _apply(slug, mutate)


def update_section(slug: str, section_id: str, patch: dict) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        target = payload.section_by_id(section_id)
        if target is None:
            raise PatchError(
                f"no section with id {slugify(section_id)!r}; "
                f"existing ids: {', '.join(s.id for s in payload.sections) or 'none'}"
            )
        merged = target.model_dump(mode="json", exclude_none=True)
        merged.update(patch)
        merged.setdefault("type", target.type)
        merged["id"] = patch.get("id", target.id)
        replacement, warnings = _coerce_section(merged)
        payload.sections[payload.sections.index(target)] = replacement
        return warnings

    return _apply(slug, mutate)


def remove_section(slug: str, section_id: str) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        target = payload.section_by_id(section_id)
        if target is None:
            raise PatchError(f"no section with id {slugify(section_id)!r}")
        payload.sections.remove(target)
        return []

    result = _apply(slug, mutate)
    # The old page file lingers otherwise, still reachable by direct URL.
    stale = config.site_dir(result["slug"]) / f"{slugify(section_id)}.html"
    if stale.is_file() and stale.name not in result["pages"]:
        stale.unlink()
    return result


def reorder_sections(slug: str, section_ids: list[str]) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        wanted = [slugify(s) for s in section_ids]
        known = {s.id: s for s in payload.sections}
        missing = [s for s in wanted if s not in known]
        if missing:
            raise PatchError(f"unknown section ids: {', '.join(missing)}")
        remaining = [s for s in payload.sections if s.id not in wanted]
        payload.sections = [known[s] for s in wanted] + remaining
        return (
            [f"sections not listed were appended in their original order: "
             f"{', '.join(s.id for s in remaining)}"]
            if remaining
            else []
        )

    return _apply(slug, mutate)


# --------------------------------------------------------------------------- #
# Flashcards
# --------------------------------------------------------------------------- #


def add_flashcard_deck(slug: str, deck: dict, section_id: str | None = None) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        section, created = _require_section(payload, section_id, "flashcards", title="Flashcards")
        parsed = Deck.model_validate(deck)
        if any(existing.id == parsed.id for existing in section.decks):
            raise PatchError(f"deck {parsed.id!r} already exists; use add_flashcards to extend it")
        section.decks.append(parsed)
        return [f"created a new flashcards section {section.id!r}"] if created else []

    return _apply(slug, mutate)


def add_flashcards(slug: str, deck_id: str, cards: list[dict], section_id: str | None = None) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        wanted = slugify(deck_id, fallback="deck")
        candidates = (
            [payload.section_by_id(section_id)] if section_id else
            [s for s in payload.sections if s.type == "flashcards"]
        )
        for section in candidates:
            if section is None or section.type != "flashcards":
                continue
            for deck in section.decks:
                if deck.id == wanted:
                    deck.cards.extend(Flashcard.model_validate(card) for card in cards)
                    return []
        known = [
            deck.id
            for s in payload.sections
            if s.type == "flashcards"
            for deck in s.decks
        ]
        raise PatchError(
            f"no deck {wanted!r}; known decks: {', '.join(known) or 'none'} "
            "(use add_flashcard_deck to create one)"
        )

    return _apply(slug, mutate)


def remove_flashcard_deck(slug: str, deck_id: str) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        wanted = slugify(deck_id, fallback="deck")
        for section in payload.sections:
            if section.type != "flashcards":
                continue
            for deck in list(section.decks):
                if deck.id == wanted:
                    section.decks.remove(deck)
                    return []
        raise PatchError(f"no deck {wanted!r}")

    return _apply(slug, mutate)


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #


def add_resources(
    slug: str,
    items: list[dict],
    group_label: str | None = None,
    kind: str | None = None,
    section_id: str | None = None,
) -> dict:
    """Append resources, merging into an existing group with the same label."""

    def mutate(payload: SitePayload) -> list[str]:
        section, created = _require_section(
            payload, section_id, "resources", title="Prerequisites — get started"
        )
        label = group_label or (kind or "other").replace("_", " ").title()
        parsed_items = [Resource.model_validate(item) for item in items]

        for group in section.groups:
            if group.label.strip().lower() == label.strip().lower():
                group.items.extend(parsed_items)
                break
        else:
            section.groups.append(
                ResourceGroup.model_validate(
                    {"label": label, "kind": kind or "other", "items": [i.model_dump(mode="json", exclude_none=True) for i in parsed_items]}
                )
            )
        return [f"created a new resources section {section.id!r}"] if created else []

    return _apply(slug, mutate)


# --------------------------------------------------------------------------- #
# Learning path, meta, theme
# --------------------------------------------------------------------------- #


def add_learning_path_step(slug: str, step: dict, position: int | None = None) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        parsed = LearningPathStep.model_validate(step)
        index = (
            len(payload.learning_path)
            if position is None
            else max(0, min(position, len(payload.learning_path)))
        )
        payload.learning_path.insert(index, parsed)
        # Step ids double as the visible numbering, so renumber after an insert.
        for number, existing in enumerate(payload.learning_path, start=1):
            existing.id = str(number)
        return []

    return _apply(slug, mutate)


def set_learning_path(slug: str, steps: list[dict]) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        payload.learning_path = [LearningPathStep.model_validate(step) for step in steps]
        return []

    return _apply(slug, mutate)


def update_meta(slug: str, patch: dict) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        if "slug" in patch and slugify(str(patch["slug"])) != payload.slug:
            raise PatchError("changing the slug would move the site URL; render a new site instead")
        merged = payload.meta.model_dump(mode="json", exclude_none=True)
        merged.update({k: v for k, v in patch.items() if k != "slug"})
        payload.meta = type(payload.meta).model_validate(merged)
        return []

    return _apply(slug, mutate)


def set_theme(slug: str, theme: dict) -> dict:
    def mutate(payload: SitePayload) -> list[str]:
        merged = payload.meta.theme.model_dump(mode="json", exclude_none=True)
        merged.update(theme)
        payload.meta.theme = Theme.model_validate(merged)
        return []

    return _apply(slug, mutate)
