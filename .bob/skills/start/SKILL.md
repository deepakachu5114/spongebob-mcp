---
name: start
description: Analyse a code repository and its docs, then render an onboarding learning site (overview, analogy based story, prerequisites, flashcards, quiz) with the spongebob MCP server and return the URL. Use when someone asks to onboard onto a repo, generate a learning site or study guide for a codebase, or wants to extend a site spongebob already rendered.
---

# start — turn a repository into a learning site

You are producing the JSON that the **spongebob** MCP server renders into a served website. spongebob owns the design; your job is content. Do not write HTML or CSS.

## 1. Verify tooling

Required: the `spongebob` MCP server. Call `get_payload_schema()` first, every time — it returns the authoritative schema plus a worked example. If anything in the schema contradicts this document, the schema takes precedence.

## 2. Read the repository

Work from the actual code, not assumptions. Read in this order and stop once you can answer the questions below:

* `README*`, `docs/`, `CONTRIBUTING*`, `ARCHITECTURE*`, ADRs, `CHANGELOG`
* the dependency manifest (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, …)
* entry points and the top-level package layout
* config, migrations, CI workflows, `Dockerfile`/`Containerfile`
* tests — they document intended behaviour more reliably than prose

Answer these before writing any JSON:

1. **What business problem does this solve, and for whom?** Not what it does — why it exists.
2. **What is the shape of the system?** The moving parts and how a request or job flows through them.
3. **What must a newcomer already understand** to read this code without getting lost?
4. **What is the smallest thing they can run** to see it work? Identify the real setup file and the real command; do not invent them.
5. **What should a newcomer be cautious about?** Non-obvious invariants, footguns, misleading naming, or notable caveats, stale README.

Use parallel subagents for the sweep when the repo is large — one per area (docs, architecture, deps, tests) — then synthesise yourself.

## 3. Gather external learning resources

By this point you have a clear picture of the tech stack. Identify 3–4 prerequisite topics a newcomer needs to understand before working with the code, and run targeted web searches for each one.

Use the project name and specific technology names as search keywords — not generic phrases. Run separate searches per topic so results do not collapse into a single domain. 

Do not keep asking permissions to run the web search tools here. 

- **YouTube tutorials**: `"<technology> tutorial site:youtube.com"` — up to 3 results with exact URLs
- **Official docs / getting-started guides**: `"<technology> getting started official documentation"` — up to 2 results
- **Coursera courses**: `"<technology> course site:coursera.org"` — up to 2 results with exact URLs
- **Developer blogs**: `"<technology> explained tutorial dev.to OR medium.com"` — up to 2 results

Do not fabricate URLs. Only include links returned by the search tool. If a category yields no strong results, omit it.

If no search tool is available, populate the resources section from links found inside the repo itself (README badges, `docs/`, `CONTRIBUTING.md`, dependency homepages) and note in your reply which resources could not be verified.

## 4. Build the overview and the analogy story

Write a 2–4 line overview of the repository: why it exists, what it solves, and how it does so. Avoid jargon — keep it accessible to someone encountering the project for the first time.

Then produce an analogy story grounded in everyday real life. The story must be professional enough for a corporate context and accessible to learners of all backgrounds — neither condescending nor overly technical. Introduce technical terms or concepts in brackets at the point where the analogy maps to them. Keep the story as short as it needs to be to convey the essential concepts.

The analogy story goes into the `overview` section's `analogies` field. Each analogy is a `title` + `body`. You may write 2–3 analogies that build on each other.

## 5. Build the guided first-task instructions

Locate the real setup file and the real command. If neither exists, identify which files to run and in what order. Do not write any files into the repository. Provide numbered, step-by-step instructions a newcomer can follow to execute a first real task, with a 1–2 sentence explanation for each step.

This goes into a `markdown` section with `id: "first-task"`. Use numbered headings and fenced code blocks for each command. Only include steps verifiable from the repository.

## 6. Build the technical deep-dive

Explain how the system works — starting from the outside (what goes in, what comes out) and drilling into the internals one level at a time. Keep explanations precise and focused.

This goes into a second `markdown` section with `id: "how-it-works"`. Use the `blocks` field for structured content (tables, callouts, code, lists) rather than raw markdown prose wherever structure aids clarity. You may also include a mermaid markdown architecture diagram here.

## 7. Build the flashcards and quiz

Flashcards and quiz questions must be grounded in the repository code, its documentation, or the external resources gathered in §3. Do not create a flashcard if you cannot verify the correct answer. Sequence both flashcards and quiz questions from easy to hard.

Every quiz question must include an `explanation` — that is where the teaching happens. Only use `mcq`, `multi`, and `true_false` question types. Wrong answer choices must be plausible, not obviously incorrect.

Split flashcards into decks by theme (`core`, `operations`, `pitfalls`). Cards should test understanding, not technical trivia — prefer "Why does X happen?" over "What version of Y is used?". Use `code` + `code_language` for snippet cards, and `hint` for a nudge toward the answer.

## 8. Assemble the payload

Target a site a learner can meaningfully work through in an afternoon: roughly 5–6 learning-path steps, 15–20 flashcards, 8-9 quiz questions.

The **section order is fixed**. Do not add arbitrary sections or invent new section types. The canonical order is:

```
overview  →  resources  →  first-task (markdown)  →  how-it-works (markdown)  →  flashcards  →  quiz
```

Each section maps to exactly one learning-path step. The `target` field in each step must be the section's `id`.

* **`meta`** — `title`, `subtitle`, `summary`, `repository` (`owner/name`), `repository_url`, `website_url`, `setup_file`, `setup_command`, `tags`.
* **`learning_path`** — one step per section, in the order above, each with a one-line `summary`, an honest `est_minutes`, and a `target` (the section id).
* **`overview`** — `business_pov` (markdown, the *why* in plain language), `analogies` (2–3, from §4), `tech_stack` (`name`, `category`, `purpose`, `version`, `docs_url` — `purpose` describes what the dependency does *in this repo*, not the vendor's tagline), `notes` for gotchas, plus `blocks` for callouts or key-value pairs worth highlighting.
* **`resources`** — group by intent, not by medium: "Watch first", "Read before you touch the scheduler", "If you have never used X". Every item needs a `title`, `url`, and a one-sentence `description` explaining why *this* link. Set `kind` (`youtube`/`blog`/`course`/`docs`/`book`/`paper`/`repo`/`tool`), `source` (`internal`/`external`), and `duration`/`level` when known.
* **`first-task` (markdown)** — the guided first task from §5. Step-by-step with fenced code blocks.
* **`how-it-works` (markdown)** — the technical internals from §6. Use `blocks` for tables, callouts, and code.
* **`flashcards`** — split into decks by theme (`core`, `operations`, `pitfalls`).
* **`quiz`** — `mcq`, `multi`, and `true_false` only. Every question requires an `explanation`.
* **`custom`** — use only when there is something critical the learner must not miss before working with the code (e.g. a known data-loss footgun, a security invariant, a prerequisite that breaks everything if skipped). Renders as a red-highlighted danger banner. Do not use for general notes or caveats — those belong in `overview.notes` or `blocks` callouts. Maximum one `custom` section per site.

Markdown is supported in most text fields; raw HTML is stripped. Link schemes are limited to http/https/mailto.

## 9. Render and report

```
render_site(payload)   →  {slug, url, pages, warnings}
```

Reply with the URL, a two-line description of what the site covers, and the `warnings` list verbatim if non-empty. Do not paste the payload back.

## 10. Follow-ups patch, never re-render

When asked to change or extend the site, use the mutators. They patch the stored payload and re-render in place, returning the same URL:

| Ask | Tool |
| --- | --- |
| more cards on an existing deck | `add_flashcards(slug, deck_id, cards)` |
| a new deck | `add_flashcard_deck(slug, deck)` |
| more links | `add_resources(slug, items, group_label, kind)` |
| fix a section's content | `update_section(slug, section_id, patch_fields)` |
| reorder / remove | `reorder_sections`, `remove_section` |
| change the path | `add_learning_path_step`, `set_learning_path` |
| hero or branding | `update_meta`, `set_theme` |

Call `get_site(slug, include_payload=true)` first when you need to inspect existing content. Only call `render_site` again for a genuinely new site — re-rendering an existing slug replaces it entirely.

## Rules

* Never invent a URL, a command, or a file path. If you cannot verify it, omit the field.
* Prefer specific over comprehensive. Five precise flashcards beat thirty vague ones.
* The site is for someone who has never seen this repo. Expand every acronym on first use.
* If the repository is too thin to support a full learning path, say so and render the smaller site you can honestly build rather than padding it.
* Do not add `add_section` calls for arbitrary extra content. Stick to the six canonical sections.
