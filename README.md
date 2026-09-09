# spongebob

An MCP server that turns an agent-authored JSON payload into a beautiful, served,
multi-page learning website — and hands back the link.

It is the rendering half of a two-part system. The other half is your own agent
("Bob"), which reads a code repository and its docs and emits the JSON. spongebob
owns the design so the agent only has to produce content.

```
repo + docs ──▶ your agent ──▶ JSON payload ──▶ spongebob ──▶ http://127.0.0.1:8787/<slug>/
```

---

## What a rendered site contains

- **Hero** — title, subtitle, repository and website links, the setup/quickstart file and command.
- **Learning path** — numbered nodes laid out in a serpentine (1→2→3, 5←4), each linking to the section it introduces.
- **Overview** — business POV, analogies, a tech-stack table, freeform blocks.
- **Prerequisites** — YouTube videos (embedded via `youtube-nocookie.com`), blog posts, courses and reference docs, grouped and tagged internal vs. external.
- **Flashcards** — decks reviewed with SM-2 spaced repetition, keyboard-driven, progress persisted in `localStorage`.
- **Quizzes** — multiple choice, multi-select, true/false and short answer, with explanations and a remembered best score.
- **Anything else** — a section type spongebob does not recognise still renders, as a generic section built from its `blocks`. Inventing new content kinds does not require a schema change.

Dark mode, print styles and deep links to every section come for free.

---

## Quick start (localhost)

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/). No Node, no build step.

```bash
# 1. Clone and install
git clone <repo-url> spongebob
cd spongebob
uv sync

# 2. Try it immediately — renders the built-in example and opens it in your browser
uv run spongebob render examples/kuya.json --open

# 3. Keep the site server running in a terminal (optional — the MCP server starts it
#    lazily too, but running it standalone keeps sites reachable after Bob exits)
uv run spongebob serve
```

Sites are served at `http://127.0.0.1:8787/<slug>/` by default.

---

## Setting up with IBM Bob

spongebob ships with ready-made Bob config files in the `.bob/` directory.
Copy them into the correct locations once and you are done.

### Step 1 — Register the MCP server

The `.bob/mcp.json` file in this repo is the workspace-scoped MCP config. Bob picks it
up automatically when you open this folder. It registers four servers:

| Server | Transport | Purpose |
| --- | --- | --- |
| `spongebob` | local (`uv run`) | renders learning sites |
| `fetch` | local (`uvx`) | fetches web pages for resource validation |
| `git` | local (`npx`) | git operations inside Bob |
| `RivalSearchMCP` | remote (HTTP) | web/academic/social search |

**Edit `.bob/mcp.json` and replace `${workspaceFolder}` with the absolute path to this repo** before opening the project in Bob:

```json
"spongebob": {
  "command": "uv",
  "args": [
    "--directory",
    "/absolute/path/to/spongebob",
    "run",
    "spongebob",
    "mcp"
  ]
}
```

> **Global alternative:** copy the same entry into `~/.bob/settings/mcp.json` under
> `mcpServers` to make spongebob available in every workspace, not just this one.

### Step 2 — Install the spongebob mode

The `.bob/custom_modes.yaml` file defines the `spongebob` mode — a focused persona with
the right tool permissions and instructions for generating onboarding sites.

Bob loads it automatically from the workspace `.bob/` directory. To make it available
globally (in all workspaces), append the entry to `~/.bob/settings/custom_modes.yaml`:

```bash
cat .bob/custom_modes.yaml >> ~/.bob/settings/custom_modes.yaml
```

### Step 3 — Verify the skill

The `start` skill lives at `.bob/skills/start/SKILL.md`. Bob discovers it automatically
from the workspace `.bob/skills/` directory — no additional steps needed.

To make it globally available, copy it to your global skills directory:

```bash
mkdir -p ~/.bob/skills/start
cp .bob/skills/start/SKILL.md ~/.bob/skills/start/SKILL.md
```

### Step 4 — Use it

1. Open any repository in Bob.
2. Switch to the **spongebob** mode (mode picker in the Bob panel).
3. Type: `onboard this repo` or `generate a learning site`.
4. Bob analyses the repo, renders the site, and returns the URL.

---

## Hosting with a container

The `Containerfile` builds a self-contained image. Use **podman** (recommended) or Docker.

### Build

```bash
podman build -t spongebob -f Containerfile .
```

### Run as a web server

Serves rendered sites on port 8787. Sites are stored in a named volume so they survive
container restarts.

```bash
podman run --rm \
  -p 8787:8787 \
  -v spongebob-sites:/data \
  spongebob
```

Sites are then reachable at `http://localhost:8787/<slug>/`.

If the host port mapping is not 1:1 (e.g. you map `9000:8787`), tell spongebob what
URL the browser will use:

```bash
podman run --rm \
  -p 9000:8787 \
  -v spongebob-sites:/data \
  -e SPONGEBOB_PUBLIC_URL=http://localhost:9000 \
  spongebob
```

### Run as an MCP server (containerised)

Connect Bob to the containerised build over stdio:

```bash
podman run --rm -i \
  -v spongebob-sites:/data \
  spongebob spongebob mcp
```

Register it in `.bob/mcp.json` (or `~/.bob/settings/mcp.json`):

```json
"spongebob": {
  "command": "podman",
  "args": [
    "run", "--rm", "-i",
    "-v", "spongebob-sites:/data",
    "spongebob",
    "spongebob", "mcp"
  ]
}
```

> **Serving sites from the MCP container:** the MCP process starts the static server
> in a background thread on first render. To keep sites reachable after Bob exits,
> run a separate `podman run … spongebob spongebob serve` container mounting the
> same `spongebob-sites` volume.

---

## CLI reference

| Command | What it does |
| --- | --- |
| `spongebob mcp` | Run the MCP server over stdio (what an MCP client launches) |
| `spongebob serve [--port N]` | Serve rendered sites in the foreground |
| `spongebob render <payload.json> [--slug S] [--open]` | Render a payload from disk |
| `spongebob list` | List rendered sites and their URLs |
| `spongebob delete <slug>` | Delete a site and its files |
| `spongebob paths` | Show the data directory and server state |

---

## MCP tools

Discovery and one-shot rendering:

- `get_payload_schema(include_example=True)` — the JSON Schema plus a worked example. Call this first.
- `render_site(payload, overwrite=True)` — returns `{slug, url, pages, warnings}`.
- `list_sites()`, `get_site(slug, include_payload=False)`, `delete_site(slug)`.

Incremental mutation — each tool patches the stored payload, re-renders, and returns
the same URL, so the agent can grow a site over several turns without resending it:

- `add_flashcard_deck`, `add_flashcards`, `remove_flashcard_deck`
- `add_resources`
- `add_section`, `update_section`, `remove_section`, `reorder_sections`
- `add_learning_path_step`, `set_learning_path`
- `update_meta`, `set_theme`

The `start` skill (`.bob/skills/start/SKILL.md`) drives the whole flow: analyse a
repo, gather resources, render, hand back the URL.

---

## Payload shape

The schema is permissive by design, because it is written by an LLM:

- unknown keys are kept and displayed rather than rejected;
- an unknown section `type` degrades to a generic section, with a warning returned from `render_site`;
- type aliases are accepted (`prerequisites` → `resources`, `test` → `quiz`, …);
- quiz answers may be an index, the choice text, a letter (`A`/`B`/`C`), a boolean, or a list for multi-select.

```jsonc
{
  "meta": {
    "title": "Kuya",
    "subtitle": "The data pipeline orchestrator",
    "repository": "acme/kuya",
    "repository_url": "https://github.com/acme/kuya",
    "website_url": "https://kuya.example.com",
    "setup_file": "docs/QUICKSTART.md",
    "setup_command": "uv sync && uv run kuya init",
    "theme": {"accent": "#22d3ee", "dark_default": true}
  },
  "learning_path": [
    {"title": "Overview", "summary": "What Kuya is for", "target": "overview", "est_minutes": 10}
  ],
  "sections": [
    {"type": "overview", "title": "Overview", "business_pov": "...",
     "analogies": [{"title": "A postal sorting office", "body": "..."}],
     "tech_stack": [{"name": "Postgres", "category": "storage", "purpose": "..."}]},
    {"type": "resources", "title": "Prerequisites", "groups": [
      {"label": "Watch first", "kind": "youtube", "items": [
        {"title": "Intro to DAGs", "url": "https://youtu.be/...", "duration": "12 min"}]}]},
    {"type": "flashcards", "title": "Flashcards", "decks": [
      {"id": "core", "name": "Core concepts", "cards": [
        {"front": "What is a DAG?", "back": "A directed acyclic graph."}]}]},
    {"type": "quiz", "title": "Knowledge check", "quizzes": [
      {"id": "basics", "name": "Basics", "questions": [
        {"prompt": "...", "kind": "mcq", "choices": ["a", "b"], "answer": "b",
         "explanation": "..."}]}]}
  ]
}
```

Run `uv run python -c "from spongebob.models import SitePayload; import json; print(json.dumps(SitePayload.model_json_schema())[:200])"` for the full schema, or just call `get_payload_schema`.

---

## Where things live

Sites are persisted outside the repo, so they survive restarts and reinstalls:

```
~/.local/share/spongebob/
  server.json              # port the static server bound
  sites/<slug>/
    payload.json           # source of truth; re-render regenerates everything else
    index.html
    overview.html ...      # one page per section
    assets/                # css + js, copied per site
```

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPONGEBOB_DATA_DIR` | `~/.local/share/spongebob` | Where sites are stored |
| `SPONGEBOB_PORT` | `8787` | Static server port (falls forward to next free port) |
| `SPONGEBOB_HOST` | `127.0.0.1` | Interface to bind |
| `SPONGEBOB_PUBLIC_URL` | _(derived)_ | Override when behind a port mapping or proxy |
| `SPONGEBOB_ACCESS_LOG` | _(off)_ | Set to any value to enable HTTP access logs |

---

## Tests

```bash
uv run python scripts/smoke_mcp.py
```

This drives the real stdio MCP protocol: lists tools, renders `examples/kuya.json`,
patches it, fetches the pages over HTTP, and asserts that error paths keep their guidance.

---

## Notes and caveats

- **Tailwind comes from a CDN.** A rendered site needs network access to look its best. The vendored `spongebob.css` carries the layout-critical pieces (learning-path connectors, card flip, progress rings), so pages stay legible offline.
- **Agent-supplied content is untrusted.** Markdown is rendered with raw HTML stripped, Jinja2 autoescapes every string, link schemes are allowlisted to `http`/`https`/`mailto`, and YouTube embeds are built from a validated video id — never from a pasted URL.
- **Flashcard progress lives in `localStorage`**, so it is per-browser and per-origin. Changing the port loses it. Fine for a local tool; worth knowing before hosting these sites for a team.
- **The server binds loopback by default.** Setting `SPONGEBOB_HOST=0.0.0.0` exposes every rendered site to your network, with no authentication.

---

## Attribution

The flashcard, quiz and spaced-repetition *concepts* are modelled on
[StudyCraft](https://github.com/rodmarkun/StudyCraft) (Apache-2.0). No StudyCraft
source code is included — see `NOTICE`.
