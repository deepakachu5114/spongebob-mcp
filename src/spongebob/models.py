"""The payload schema an upstream agent fills in.

Design notes
------------
Every model allows extra fields (``extra="allow"``). The upstream author is an
LLM, so the schema is deliberately forgiving: unknown keys survive validation
and are surfaced on the page as a generic key/value block instead of causing a
hard failure. Section and resource ``type``/``kind`` strings are run through an
alias table for the same reason.

The one place we are strict is URLs: an unsafe scheme is a validation error
rather than a silent drop, because a silently-missing link is worse than a
clear message the agent can act on.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto"})
HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")


def slugify(value: str, fallback: str = "site") -> str:
    """Lowercase, ASCII, hyphen-separated. Used for site slugs and page names."""
    normalised = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or fallback


def _check_url(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    match = SCHEME_RE.match(candidate)
    if not match:
        return candidate  # relative link or bare id resolved inside the rendered site
    scheme = match.group(1).lower()
    if scheme not in SAFE_URL_SCHEMES:
        raise ValueError(
            f"URL scheme {scheme!r} in {value!r} is not allowed "
            f"(permitted: {', '.join(sorted(SAFE_URL_SCHEMES))})"
        )
    return candidate


Url = Annotated[str | None, Field(default=None)]


class Base(BaseModel):
    """Permissive base: keeps unrecognised keys so new ideas round-trip."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, str_strip_whitespace=True)

    def extras(self) -> dict[str, Any]:
        """Fields the agent supplied that this schema does not know about."""
        return dict(self.__pydantic_extra__ or {})


# --------------------------------------------------------------------------- #
# Leaf content types
# --------------------------------------------------------------------------- #


class Theme(Base):
    accent: str = "#6366f1"
    accent_soft: str | None = None
    dark_default: bool = True

    @field_validator("accent", "accent_soft")
    @classmethod
    def _hex_only(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not HEX_COLOUR.match(v):
            raise ValueError(f"colour {v!r} must be a hex value like #6366f1")
        return v


class SiteMeta(Base):
    title: str
    slug: str | None = None
    subtitle: str | None = None
    summary: str | None = None
    repository: str | None = None
    repository_url: str | None = None
    website_url: str | None = None
    setup_file: str | None = None
    setup_command: str | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    theme: Theme = Field(default_factory=Theme)

    @field_validator("repository_url", "website_url")
    @classmethod
    def _urls(cls, v: str | None) -> str | None:
        return _check_url(v)

    @model_validator(mode="after")
    def _derive_slug(self) -> SiteMeta:
        if not self.slug:
            self.slug = slugify(self.title)
        else:
            self.slug = slugify(self.slug)
        return self


class LearningPathStep(Base):
    title: str
    id: str | None = None
    summary: str | None = None
    target: str | None = None
    est_minutes: int | None = None

    @field_validator("target")
    @classmethod
    def _target(cls, v: str | None) -> str | None:
        return _check_url(v)


class Analogy(Base):
    title: str
    body: str


class TechItem(Base):
    name: str
    category: str | None = None
    purpose: str | None = None
    version: str | None = None
    docs_url: str | None = None

    @field_validator("docs_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _check_url(v)


RESOURCE_KIND_ALIASES = {
    "video": "youtube",
    "videos": "youtube",
    "yt": "youtube",
    "youtube": "youtube",
    "article": "blog",
    "articles": "blog",
    "post": "blog",
    "blog": "blog",
    "blogs": "blog",
    "course": "course",
    "courses": "course",
    "doc": "docs",
    "docs": "docs",
    "documentation": "docs",
    "reference": "docs",
    "book": "book",
    "books": "book",
    "paper": "paper",
    "papers": "paper",
    "repo": "repo",
    "tool": "tool",
}
ResourceKind = Literal["youtube", "blog", "course", "docs", "book", "paper", "repo", "tool", "other"]


class Resource(Base):
    title: str
    url: str
    description: str | None = None
    kind: ResourceKind | None = None
    source: Literal["internal", "external"] | None = None
    author: str | None = None
    duration: str | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        checked = _check_url(v)
        if not checked:
            raise ValueError("resource url must not be empty")
        return checked

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Any:
        if isinstance(v, str):
            return RESOURCE_KIND_ALIASES.get(v.strip().lower(), v.strip().lower())
        return v


class ResourceGroup(Base):
    label: str
    kind: ResourceKind = "other"
    description: str | None = None
    items: list[Resource] = Field(default_factory=list)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Any:
        if isinstance(v, str):
            return RESOURCE_KIND_ALIASES.get(v.strip().lower(), v.strip().lower())
        return v

    @model_validator(mode="after")
    def _inherit_kind(self) -> ResourceGroup:
        for item in self.items:
            if item.kind is None:
                item.kind = self.kind
        return self


class Flashcard(Base):
    front: str
    back: str
    id: str | None = None
    hint: str | None = None
    code: str | None = None
    code_language: str | None = None
    tags: list[str] = Field(default_factory=list)


class Deck(Base):
    name: str
    id: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    cards: list[Flashcard] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids(self) -> Deck:
        self.id = slugify(self.id or self.name, fallback="deck")
        for index, card in enumerate(self.cards, start=1):
            if not card.id:
                card.id = f"{self.id}-{index}"
        return self


QUESTION_KIND_ALIASES = {
    "single": "mcq",
    "single_choice": "mcq",
    "multiple_choice": "mcq",
    "choice": "mcq",
    "mcq": "mcq",
    "multi": "multi",
    "multi_select": "multi",
    "multiple": "multi",
    "checkbox": "multi",
    "boolean": "true_false",
    "bool": "true_false",
    "true_false": "true_false",
    "truefalse": "true_false",
    "short": "short",
    "short_answer": "short",
    "text": "short",
    "open": "short",
}


class Question(Base):
    prompt: str
    id: str | None = None
    kind: Literal["mcq", "multi", "true_false", "short"] = "mcq"
    choices: list[str] = Field(default_factory=list)
    answer: Any = None
    explanation: str | None = None

    # Normalised forms the frontend consumes.
    answer_indices: list[int] = Field(default_factory=list)
    answer_text: str | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Any:
        if isinstance(v, str):
            return QUESTION_KIND_ALIASES.get(v.strip().lower(), v.strip().lower())
        return v

    @model_validator(mode="after")
    def _normalise_answer(self) -> Question:
        if self.kind == "true_false" and not self.choices:
            self.choices = ["True", "False"]

        if self.kind == "short":
            if self.answer is not None and self.answer_text is None:
                self.answer_text = str(self.answer)
            return self

        if self.answer_indices:
            return self

        raw = self.answer
        candidates = raw if isinstance(raw, list) else [raw]
        lowered = [c.strip().lower() for c in self.choices]
        indices: list[int] = []
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, bool):
                indices.append(0 if candidate else 1)
            elif isinstance(candidate, int):
                indices.append(candidate)
            else:
                text = str(candidate).strip()
                if text.lower() in lowered:
                    indices.append(lowered.index(text.lower()))
                elif len(text) == 1 and text.upper().isalpha():
                    # "A" / "B" / "C" style answers
                    indices.append(ord(text.upper()) - ord("A"))
                else:
                    raise ValueError(
                        f"answer {candidate!r} for question {self.prompt!r} does not match any choice"
                    )
        bad = [i for i in indices if i < 0 or i >= len(self.choices)]
        if bad:
            raise ValueError(f"answer index {bad[0]} is out of range for question {self.prompt!r}")
        self.answer_indices = sorted(set(indices))
        return self


class Quiz(Base):
    name: str
    id: str | None = None
    description: str | None = None
    pass_score: int | None = None
    questions: list[Question] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids(self) -> Quiz:
        self.id = slugify(self.id or self.name, fallback="quiz")
        for index, question in enumerate(self.questions, start=1):
            if not question.id:
                question.id = f"{self.id}-q{index}"
        return self


class Block(Base):
    """One freeform chunk of content, usable inside any section.

    A single permissive model rather than a union — it is far more tolerant of
    LLM-authored content, and unused fields simply render as nothing.
    """

    type: str = "markdown"
    title: str | None = None
    text: str | None = None
    level: int | None = None
    items: list[str] = Field(default_factory=list)
    links: list[Resource] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    pairs: dict[str, str] = Field(default_factory=dict)
    language: str | None = None
    variant: str | None = None
    url: str | None = None
    alt: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _check_url(v)


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


class SectionBase(Base):
    title: str
    id: str | None = None
    subtitle: str | None = None
    icon: str | None = None
    page: bool = True
    blocks: list[Block] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_id(self) -> SectionBase:
        self.id = slugify(self.id or self.title, fallback=self.type)  # type: ignore[attr-defined]
        return self

    @property
    def filename(self) -> str:
        return f"{self.id}.html"


class OverviewSection(SectionBase):
    type: Literal["overview"] = "overview"
    business_pov: str | None = None
    analogies: list[Analogy] = Field(default_factory=list)
    tech_stack: list[TechItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ResourcesSection(SectionBase):
    type: Literal["resources"] = "resources"
    groups: list[ResourceGroup] = Field(default_factory=list)


class FlashcardsSection(SectionBase):
    type: Literal["flashcards"] = "flashcards"
    decks: list[Deck] = Field(default_factory=list)


class QuizSection(SectionBase):
    type: Literal["quiz"] = "quiz"
    quizzes: list[Quiz] = Field(default_factory=list)


class MarkdownSection(SectionBase):
    type: Literal["markdown"] = "markdown"
    body: str = ""


class CustomSection(SectionBase):
    type: Literal["custom"] = "custom"


Section = Annotated[
    Union[
        OverviewSection,
        ResourcesSection,
        FlashcardsSection,
        QuizSection,
        MarkdownSection,
        CustomSection,
    ],
    Field(discriminator="type"),
]

SECTION_TYPES = ("overview", "resources", "flashcards", "quiz", "markdown", "custom")

SECTION_TYPE_ALIASES = {
    "overview": "overview",
    "intro": "overview",
    "introduction": "overview",
    "about": "overview",
    "summary": "overview",
    "resources": "resources",
    "resource": "resources",
    "prerequisites": "resources",
    "prerequisite": "resources",
    "prereqs": "resources",
    "links": "resources",
    "learning_resources": "resources",
    "getting_started": "resources",
    "flashcards": "flashcards",
    "flashcard": "flashcards",
    "cards": "flashcards",
    "deck": "flashcards",
    "decks": "flashcards",
    "quiz": "quiz",
    "quizzes": "quiz",
    "test": "quiz",
    "tests": "quiz",
    "assessment": "quiz",
    "markdown": "markdown",
    "md": "markdown",
    "text": "markdown",
    "prose": "markdown",
    "custom": "custom",
}


def normalise_section(raw: Any, warnings: list[str]) -> Any:
    """Map a raw section dict onto a known ``type``.

    Unrecognised types degrade to ``custom`` with a warning rather than failing,
    so the agent can invent section kinds we have not implemented yet and still
    get a rendered page.
    """
    if not isinstance(raw, dict):
        return raw
    raw = dict(raw)
    declared = raw.get("type")
    key = str(declared).strip().lower() if declared is not None else ""
    resolved = SECTION_TYPE_ALIASES.get(key)

    if resolved is None:
        if not key:
            resolved = "custom"
            warnings.append(
                f"section {raw.get('title', '(untitled)')!r} has no 'type'; rendered as a custom section"
            )
        else:
            resolved = "custom"
            raw.setdefault("original_type", key)
            warnings.append(
                f"unknown section type {key!r} on {raw.get('title', '(untitled)')!r}; "
                "rendered as a custom section (known types: " + ", ".join(SECTION_TYPES) + ")"
            )
    elif resolved != key:
        warnings.append(f"section type {key!r} interpreted as {resolved!r}")

    raw["type"] = resolved
    return raw


class SitePayload(Base):
    """The whole site. This is what an agent hands to ``render_site``."""

    version: Literal[1] = 1
    meta: SiteMeta
    learning_path: list[LearningPathStep] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    footer_note: str | None = None
    warnings: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        warnings: list[str] = list(data.get("warnings") or [])
        sections = data.get("sections")
        if isinstance(sections, list):
            data["sections"] = [normalise_section(s, warnings) for s in sections]
        data["warnings"] = warnings
        return data

    @model_validator(mode="after")
    def _unique_ids(self) -> SitePayload:
        seen: dict[str, int] = {}
        for section in self.sections:
            base = section.id or "section"
            if base in seen:
                seen[base] += 1
                section.id = f"{base}-{seen[base]}"
                self.warnings.append(f"duplicate section id {base!r}; renamed to {section.id!r}")
            else:
                seen[base] = 1
        for index, step in enumerate(self.learning_path, start=1):
            if not step.id:
                step.id = str(index)
        return self

    @property
    def slug(self) -> str:
        return self.meta.slug or slugify(self.meta.title)

    def section_by_id(self, section_id: str) -> Any:
        target = slugify(section_id)
        for section in self.sections:
            if section.id == target:
                return section
        return None

    def first_section_of_type(self, section_type: str) -> Any:
        for section in self.sections:
            if section.type == section_type:
                return section
        return None
