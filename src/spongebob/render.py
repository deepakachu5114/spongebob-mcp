"""Turn a validated :class:`SitePayload` into a multi-page static site.

The scaffold is fixed: an index page carrying the hero and the learning path,
one page per section, and a shared asset bundle. The agent supplies content
only, never layout.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup, escape
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from . import config, store
from .models import SCHEME_RE, SitePayload, slugify

PACKAGE_DIR = Path(__file__).parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
ASSETS_DIRNAME = "assets"

SECTION_TEMPLATES = {
    "overview": "overview.html",
    "resources": "resources.html",
    "flashcards": "flashcards.html",
    "quiz": "quiz.html",
    "markdown": "markdown.html",
    "custom": "custom.html",
}

DEFAULT_ICONS = {
    "overview": "compass",
    "resources": "book",
    "flashcards": "cards",
    "quiz": "check",
    "markdown": "document",
    "custom": "layers",
}


@dataclass
class RenderResult:
    slug: str
    directory: Path
    pages: list[str]
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def _highlight(code: str, language: str, _attrs: str) -> str:
    try:
        lexer = get_lexer_by_name(language) if language else guess_lexer(code)
    except (ClassNotFound, ValueError):
        return ""  # let markdown-it fall back to a plain escaped <pre>
    formatter = HtmlFormatter(nowrap=False, cssclass="sb-code")
    return highlight(code, lexer, formatter)


def _markdown() -> MarkdownIt:
    # html=False keeps agent-authored markdown from injecting raw HTML, and
    # markdown-it's own validateLink already rejects javascript:/vbscript: hrefs.
    md = MarkdownIt("commonmark", {"html": False, "highlight": _highlight, "typographer": True})
    md.enable(["table", "strikethrough", "smartquotes", "replacements"])
    return md


_MD = _markdown()


# These return Markup, not str: the HTML is ours, produced by markdown-it with
# html=False (agent-authored raw HTML is stripped) and by Pygments, which escapes
# the code it formats. Returning plain str would make Jinja's autoescape render
# our own tags as visible text.


def render_markdown(text: str | None) -> Markup:
    if not text:
        return Markup("")
    return Markup(_MD.render(str(text)))


def render_markdown_inline(text: str | None) -> Markup:
    if not text:
        return Markup("")
    return Markup(_MD.renderInline(str(text)))


def highlight_code(source: str | None, language: str | None) -> Markup:
    if not source:
        return Markup("")
    rendered = _highlight(str(source), (language or "").strip(), "")
    if rendered:
        return Markup(rendered)
    return Markup(f'<pre class="sb-code"><code>{escape(source)}</code></pre>')


# --------------------------------------------------------------------------- #
# Link helpers
# --------------------------------------------------------------------------- #

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def youtube_id(url: str | None) -> str | None:
    """Extract a video id so we can embed via youtube-nocookie instead of
    dropping a caller-supplied URL straight into an iframe src."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.hostname not in _YT_HOSTS:
        return None
    candidate = None
    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        values = parse_qs(parsed.query).get("v")
        candidate = values[0] if values else None
    elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
        candidate = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None
    if candidate and _YT_ID.match(candidate):
        return candidate
    return None


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def resolve_target(target: str | None, section_ids: set[str]) -> str | None:
    """Learning-path targets may be a full URL, a page filename, an anchor, or
    just a section id. Normalise to an in-page anchor (#id) so the site stays
    on one scrolling page."""
    if not target:
        return None
    if SCHEME_RE.match(target) or target.startswith(("/", "#", "./", "../")):
        return target
    if target.endswith(".html"):
        # Convert legacy .html links to in-page anchors
        candidate = target[: -len(".html")]
        if candidate in section_ids:
            return f"#{candidate}"
        return target
    candidate = slugify(target)
    if candidate in section_ids:
        return f"#{candidate}"
    return target


# --------------------------------------------------------------------------- #
# Template globals
# --------------------------------------------------------------------------- #


_JSON_ESCAPES = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}


def json_script(value) -> Markup:
    """Serialise for embedding in a ``<script type="application/json">`` block.

    The payload is marked safe (JSON must not be HTML-escaped or the browser
    cannot parse it), so ``<``, ``>`` and ``&`` are escaped as JSON unicode
    sequences instead — that keeps a ``</script>`` inside agent-supplied content
    from ending the block early.
    """
    text = json.dumps(value, ensure_ascii=False)
    for char, replacement in _JSON_ESCAPES.items():
        text = text.replace(char, replacement)
    return Markup(text)


def summarise_section(section) -> str:
    """One-line stat for a section card on the index page."""
    if section.type == "resources":
        count = sum(len(group.items) for group in section.groups)
        return f"{count} resource{'s' if count != 1 else ''} in {len(section.groups)} groups"
    if section.type == "flashcards":
        cards = sum(len(deck.cards) for deck in section.decks)
        return f"{cards} card{'s' if cards != 1 else ''} across {len(section.decks)} decks"
    if section.type == "quiz":
        questions = sum(len(quiz.questions) for quiz in section.quizzes)
        return f"{questions} question{'s' if questions != 1 else ''}"
    if section.type == "overview":
        bits = []
        if section.analogies:
            bits.append(f"{len(section.analogies)} analogies")
        if section.tech_stack:
            bits.append(f"{len(section.tech_stack)} components")
        return ", ".join(bits) or "Read the overview"
    if section.type == "markdown":
        words = len((section.body or "").split())
        return f"~{max(1, round(words / 200))} min read"
    return f"{len(section.blocks)} block{'s' if len(section.blocks) != 1 else ''}"


def deck_data(section):
    """Markdown in flashcards is rendered server-side, so the browser only ever
    inserts HTML that came out of our own sanitising markdown pipeline."""
    decks = []
    for deck in section.decks:
        decks.append(
            {
                "id": deck.id,
                "name": deck.name,
                "description": deck.description,
                "tags": list(deck.tags),
                "cards": [
                    {
                        "id": card.id,
                        "front": render_markdown(card.front),
                        "back": render_markdown(card.back),
                        "hint": render_markdown_inline(card.hint) if card.hint else None,
                        "code": highlight_code(card.code, card.code_language) if card.code else None,
                        "tags": list(card.tags),
                    }
                    for card in deck.cards
                ],
            }
        )
    return json_script(decks)


def quiz_data(section):
    quizzes = []
    for quiz in section.quizzes:
        quizzes.append(
            {
                "id": quiz.id,
                "name": quiz.name,
                "description": quiz.description,
                "passScore": quiz.pass_score,
                "questions": [
                    {
                        "id": question.id,
                        "kind": question.kind,
                        "prompt": render_markdown(question.prompt),
                        "choices": [render_markdown_inline(c) for c in question.choices],
                        "answerIndices": list(question.answer_indices),
                        "answerText": question.answer_text,
                        "explanation": render_markdown(question.explanation) if question.explanation else None,
                    }
                    for question in quiz.questions
                ],
            }
        )
    return json_script(quizzes)


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #


def build_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(default_for_string=True, default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["md"] = render_markdown
    env.filters["md_inline"] = render_markdown_inline
    env.filters["code"] = highlight_code
    env.filters["youtube_id"] = youtube_id
    env.filters["domain"] = domain_of
    env.filters["tojson_safe"] = lambda value: json.dumps(value, ensure_ascii=False)
    env.globals["json_script"] = json_script
    env.globals["summarise_section"] = summarise_section
    env.globals["deck_data"] = deck_data
    env.globals["quiz_data"] = quiz_data
    # Custom Jinja2 test: {% ... | rejectattr("type", "in", [...]) %}
    env.tests["in"] = lambda value, seq: value in seq
    return env


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _nav(payload: SitePayload) -> list[dict]:
    items = [{"label": "Start", "href": "index.html", "id": "__index__"}]
    for section in payload.sections:
        if not section.page:
            continue
        items.append({"label": section.title, "href": section.filename, "id": section.id})
    return items


def _context(payload: SitePayload, env_pages: list[dict]) -> dict:
    section_ids = {s.id for s in payload.sections if s.id}
    steps = []
    for index, step in enumerate(payload.learning_path, start=1):
        steps.append(
            {
                "number": index,
                "label": step.id or str(index),
                "title": step.title,
                "summary": step.summary,
                "href": resolve_target(step.target, section_ids),
                "est_minutes": step.est_minutes,
            }
        )
    minutes = sum(step.est_minutes or 0 for step in payload.learning_path)
    return {
        "meta": payload.meta,
        "total_minutes": minutes or None,
        "theme": payload.meta.theme,
        "payload": payload,
        "steps": steps,
        "nav": _nav(payload),
        "sections": payload.sections,
        "inline_sections": [s for s in payload.sections if not s.page],
        "assets": ASSETS_DIRNAME,
        "footer_note": payload.footer_note,
        "pages": env_pages,
        "generator_version": _version(),
        "section_templates": SECTION_TEMPLATES,
        "default_icons": DEFAULT_ICONS,
    }


def _version() -> str:
    from . import __version__

    return __version__


def _copy_assets(directory: Path) -> None:
    target = directory / ASSETS_DIRNAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(STATIC_DIR, target)
    # Pygments needs a stylesheet to go with the markup it emits. Light and dark
    # variants live in one file, the dark half scoped under `.dark`.
    light = HtmlFormatter(cssclass="sb-code", style="default")
    dark = HtmlFormatter(cssclass="sb-code", style="one-dark")
    (target / "pygments.css").write_text(
        "/* generated by spongebob */\n"
        + light.get_style_defs(".sb-code")
        + "\n"
        + dark.get_style_defs(".dark .sb-code")
        + "\n",
        encoding="utf-8",
    )


def render_site(payload: SitePayload, *, persist: bool = True) -> RenderResult:
    """Write the whole site to disk. Idempotent — safe to call after every patch."""
    config.ensure_dirs()
    slug = store.safe_slug(payload.slug)
    directory = config.site_dir(slug)
    directory.mkdir(parents=True, exist_ok=True)

    env = build_environment()
    page_list = [{"href": "index.html", "title": payload.meta.title, "id": "__index__"}] + [
        {"href": s.filename, "title": s.title, "id": s.id} for s in payload.sections if s.page
    ]
    context = _context(payload, page_list)

    written: list[str] = []

    index_html = env.get_template("index.html").render(
        **context, current="__index__", page_title=payload.meta.title
    )
    (directory / "index.html").write_text(index_html, encoding="utf-8")
    written.append("index.html")

    for section in payload.sections:
        if not section.page:
            continue
        template_name = SECTION_TEMPLATES.get(section.type, "custom.html")
        html = env.get_template(template_name).render(
            **context,
            section=section,
            current=section.id,
            page_title=f"{section.title} · {payload.meta.title}",
        )
        (directory / section.filename).write_text(html, encoding="utf-8")
        written.append(section.filename)

    _copy_assets(directory)

    if persist:
        store.save_payload(payload)

    render_site_index()

    return RenderResult(slug=slug, directory=directory, pages=written, warnings=list(payload.warnings))


def render_site_index() -> Path:
    """Regenerate the landing page at ``/`` that lists every rendered site."""
    config.ensure_dirs()
    env = build_environment()
    summaries = store.list_sites()
    html = env.get_template("site_index.html").render(
        sites=summaries, generator_version=_version()
    )
    target = config.sites_dir() / "index.html"
    target.write_text(html, encoding="utf-8")
    return target
