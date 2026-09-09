---
name: start
description: Analyse a code repository and its docs, then render an onboarding learning site (overview, analogy based story, prerequisites, flashcards, quiz) with the spongebob MCP server and return the URL. Use when someone asks to onboard onto a repo, generate a learning site or study guide for a codebase, or wants to extend a site spongebob already rendered.
---

# start — turn a repository into a learning site

You are producing the JSON that the **spongebob** MCP server renders into a served website. spongebob owns the design; your job is content. Do not write HTML
or CSS.

## 1. Check the tools you have

Required: the `spongebob` MCP server. Call `get_payload_schema()` first, every time —
it returns the authoritative schema plus a worked example. Follow that over anything
written here if the two disagree.

Optional, and worth using when connected to gather External Learning Resources:

Use a web search tool to find real, specific, linkable resources. Make separate targeted searches for each category below. Use the **actual project name and primary tech stack** as keywords.

- **YouTube tutorials**: search `"<project-tech> tutorial site:youtube.com"` — return up to 3 results with exact URLs
- **Official docs / blogs**: search `"<project-tech> getting started official documentation"` — return up to 2 results
- **IBM w3 internal**: search `"<project-tech> IBM w3 internal tutorial site:w3.ibm.com"` — include if results are found; skip if none
- **Coursera**: search `"<project-tech> course site:coursera.org"` — return up to 2 results with exact URLs
- **Dev blogs**: search `"<project-tech> explained tutorial dev.to OR medium.com"` — return up to 2 results

Do NOT fabricate links. Only include URLs returned by the tool. If a category returns no good results, omit it.

If no search tool is available, still produce the resources section from links you find in
the repo itself (README badges, `docs/`, `CONTRIBUTING.md`, dependency homepages) and
say in your reply which resources you could not verify.

## 2. Read the repository

Work from the actual code, not assumptions. Read in this order and stop when you can
answer the questions below:

* `README*`, `docs/`, `CONTRIBUTING*`, `ARCHITECTURE*`, ADRs, `CHANGELOG`
* the dependency manifest (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, …)
* entry points and the top-level package layout
* config, migrations, CI workflows, `Dockerfile`/`Containerfile`
* tests — they document intended behaviour better than prose usually does

Answer these before you write any JSON:

1. **What business problem does this solve, and for whom?** Not what it does — why it
   exists.
2. **What is the shape of the system?** The moving parts and how a request or job
   flows through them.
3. **What must a newcomer already understand** to read this code without drowning?
4. **What is the smallest thing they can run** to see it work? Find the real setup
   file and the real command; do not invent them.
5. **What are the things a newcomer should be wary of?** Non-obvious invariants, footguns, naming that misleads, or any caveats.

Use parallel subagents for the sweep when the repo is large — one per area (docs,
architecture, deps, tests) — then synthesise yourself.

## 3. Build the overview and the analogy story

Write an overview of the repository (why it exists, what it solves and how, 2-4 lines).

To make the learning process engaging and to ease the learner's anxiety, do not use overly
technical terms in the overview. Keep it as layman friendly as possible.

In the next step, generate an analogy story or a scenario that is grounded in everyday real life that is NOT overly kiddish and
NOT inappropriate from a corporate perspective. The story should be engaging to learners of all ages and make the concepts
easy to understand through the analogies. Introduce the technical terms or concepts in brackets as and when you make an analogy for that particular
term or concept in the story. Don't drag the story too long, only make it as long as it needs to be to give the user a gist of the
technicalities without overburdening them.

The analogy story goes into the `overview` section's `analogies` field — each analogy is a `title` + `body`. Write 2–3 analogies that together tell this story progressively.

## 4. Build the instructions for a guided first task

Find the real setup file and the real command. If they do not exist, just give the instructions on which files to run and in what order.
Do NOT write files into the repository by yourself. Give step by step instructions on how to run the files (setup or otherwise), so that
the user can execute a first real task. Give 1-2 liner explanation for each step in the process.

This goes into a `markdown` section with `id: "first-task"`. Use numbered headings and fenced code blocks for each command. Never invent a command or path — only include steps you can verify from the repository.

## 5. Build the technical nitty gritties

How it works — starting from the outside (what you put in, what comes out) and drilling into the internals one level at a time. Keep it explanatory and to the point.

This goes into a second `markdown` section with `id: "how-it-works"`. Use the `blocks` field for structured content (tables, callouts, code, lists) rather than raw markdown prose wherever structure helps clarity.

## 6. Build the flashcards and the quiz

The flashcards should strictly be based on the repository code, the docs or the external resources that you found. If you don't know the correct
answer to a flashcard, do NOT create it. Make sure the flashcards start with easy questions and get progressively harder. Same applies for quiz. Make
sure all the questions in quiz have an explanation (that is where the teaching happens), and all of the questions should be based on the knowledge available in the flash cards and the reading
material the user has access to. Do NOT make questions that require the user to answer in words — make only `mcq`, `multi`, and `true_false` questions. Wrong choices should be plausible.

Split flashcards into decks by theme (`core`, `operations`, `pitfalls`). Cards test understanding, not trivia: prefer "Why does X happen?" over "What version of Y is used?". Use `code` + `code_language` for snippet cards, `hint` for a nudge.

## 7. Build the payload

Aim for a site someone could actually learn from in an afternoon: roughly 5–6
learning-path steps, 15–30 flashcards, 10–15 quiz questions.

The **section order is fixed**. Do not add arbitrary sections or invent new section types. The canonical flow is:

```
overview  →  resources  →  first-task (markdown)  →  how-it-works (markdown)  →  flashcards  →  quiz
```

Each section maps to exactly one learning-path step. The `target` field in each step must be the section's `id` (an in-page anchor, e.g. `"overview"`).

* **`meta`** — `title`, `subtitle`, `summary`, `repository` (`owner/name`),
  `repository_url`, `website_url`, `setup_file`, `setup_command`, `tags`.
* **`learning_path`** — one step per section, in the order above, each
  with a one-line `summary`, an honest `est_minutes`, and a `target` (the section id).
* **`overview`** — `business_pov` (markdown, the *why* in plain language), `analogies` (2–3, the story from §3),
  `tech_stack` (`name`, `category`, `purpose`, `version`, `docs_url` — purpose means "what it does
  *in this repo*", not the vendor's tagline), `notes` for gotchas, plus `blocks` for any
  callouts or key-value pairs worth highlighting.
* **`resources`** — group by intent, not by medium: "Watch first", "Read before you
  touch the scheduler", "If you have never used X". Every item needs a `title`, `url`
  and a one-sentence `description` saying why *this* link. Set `kind`
  (`youtube`/`blog`/`course`/`docs`/`book`/`paper`/`repo`/`tool`), `source`
  (`internal`/`external`), and `duration`/`level` when known.
* **`first-task` (markdown)** — the guided first task from §4. Step-by-step with fenced code blocks.
* **`how-it-works` (markdown)** — the technical internals from §5. Use `blocks` for tables, callouts, and code.
* **`flashcards`** — split into decks by theme (`core`, `operations`, `pitfalls`).
* **`quiz`** — `mcq`, `multi`, and `true_false` only. Every question needs an `explanation`.
* **`custom`** — **use only when there is something critical the learner must not miss before working with the code** (e.g. a known data-loss footgun, a security invariant, a prerequisite that breaks everything if skipped). It renders as a red-highlighted danger banner (Carbon Red, left-bordered). Do not use it for general notes or caveats — those belong in `overview.notes` or `blocks` callouts. One `custom` section per site, maximum.

Markdown works in most text fields; raw HTML is stripped. Link schemes are limited to
http/https/mailto.

## 8. Render and report

```
render_site(payload)   →  {slug, url, pages, warnings}
```

Then reply with the URL, a two-line description of what the site covers, and the
`warnings` list verbatim if it is non-empty. Do not paste the payload back.

## 9. Follow-ups patch, never re-render

When asked to change or extend the site, use the mutators. They patch the stored
payload and re-render in place, returning the same URL:

| Ask | Tool |
| --- | --- |
| more cards on an existing deck | `add_flashcards(slug, deck_id, cards)` |
| a new deck | `add_flashcard_deck(slug, deck)` |
| more links | `add_resources(slug, items, group_label, kind)` |
| fix a section's content | `update_section(slug, section_id, patch_fields)` |
| reorder / remove | `reorder_sections`, `remove_section` |
| change the path | `add_learning_path_step`, `set_learning_path` |
| hero or branding | `update_meta`, `set_theme` |

Call `get_site(slug, include_payload=true)` first when you need to know what is
already there. Only call `render_site` again for a genuinely new site — re-rendering
an existing slug replaces it.

## Rules

* Never invent a URL, a command or a file path. If you cannot verify it, leave the
  field out.
* Prefer specific over comprehensive. Five sharp flashcards beat thirty vague ones.
* The site is for a person who has never seen this repo. Expand every acronym once.
* If the repo is too thin to support a real learning path, say so and render the
  smaller site you can honestly build, rather than padding it.
* Do not add `add_section` calls for arbitrary extra content. Stick to the six canonical sections.
