#!/usr/bin/env python3
"""End-to-end MCP smoke test.

Launches `spongebob mcp` over stdio exactly the way a real MCP client does,
renders the example payload, patches it, then fetches the resulting page over
HTTP to prove the URL actually serves something.

    uv run python scripts/smoke_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "kuya.json"


def _text(result) -> str:
    return "\n".join(block.text for block in result.content if getattr(block, "text", None))


def _payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(_text(result))


def _check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        raise SystemExit(1)


async def main() -> None:
    env = dict(os.environ)
    env.setdefault("SPONGEBOB_DATA_DIR", "/tmp/spongebob-smoke")
    env.setdefault("SPONGEBOB_PORT", "8799")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "spongebob.cli", "mcp"],
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"connected to {init.server_info.name} {init.server_info.version}")

            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            print(f"\n{len(tools)} tools exposed")
            for required in (
                "get_payload_schema",
                "render_site",
                "add_flashcards",
                "add_resources",
                "add_section",
            ):
                _check(required in names, f"tool {required} present")

            schema = _payload(await session.call_tool("get_payload_schema", {"include_example": False}))
            _check("json_schema" in schema, "get_payload_schema returns a schema")

            print("\nrendering the example payload")
            payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            rendered = _payload(await session.call_tool("render_site", {"payload": payload}))
            url = rendered["url"]
            print(f"  url: {url}")
            _check(len(rendered["pages"]) >= 6, f"{len(rendered['pages'])} pages written")
            _check(
                any("architecture-deep-dive" in w for w in rendered["warnings"]),
                "unknown section type reported as a warning",
            )

            print("\npatching the rendered site")
            patched = _payload(
                await session.call_tool(
                    "add_flashcards",
                    {
                        "slug": "kuya",
                        "deck_id": "core",
                        "cards": [{"front": "SMOKE-CARD-FRONT", "back": "SMOKE-CARD-BACK"}],
                    },
                )
            )
            _check(patched["url"] == url, "patch returns the same URL")

            _payload(
                await session.call_tool(
                    "add_section",
                    {
                        "slug": "kuya",
                        "section": {
                            "type": "totally-made-up",
                            "title": "Smoke Section",
                            "blocks": [{"type": "markdown", "text": "SMOKE-BLOCK"}],
                        },
                    },
                )
            )
            summary = _payload(await session.call_tool("get_site", {"slug": "kuya"}))
            _check(
                any(s["id"] == "smoke-section" for s in summary["sections"]),
                "invented section type was accepted and rendered",
            )

            print("\nfetching pages over HTTP")
            for page, needle in [
                ("", "Learning path"),
                ("flashcards.html", "SMOKE-CARD-FRONT"),
                ("smoke-section.html", "SMOKE-BLOCK"),
                ("knowledge-check.html", "data-quiz-data"),
            ]:
                with urllib.request.urlopen(url + page, timeout=5) as response:  # noqa: S310
                    body = response.read().decode("utf-8")
                _check(response.status == 200 and needle in body, f"GET /{page or 'index'} contains {needle!r}")

            listing = _payload(await session.call_tool("list_sites", {}))
            _check(any(s["slug"] == "kuya" for s in listing["sites"]), "site appears in list_sites")

            print("\nmarkdown and code render as HTML, not as escaped text")
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                index = response.read().decode("utf-8")
            for leak in ("&lt;p&gt;", "&lt;pre&gt;", "&lt;div", "&lt;span"):
                _check(leak not in index, f"no double-escaped {leak!r} on the index page")
            _check("<p>" in index, "markdown produced real <p> tags")

            print("\nerror paths keep their guidance")
            for tool, arguments, needle in [
                ("add_flashcards", {"slug": "kuya", "deck_id": "nope", "cards": []}, "known decks"),
                ("get_site", {"slug": "missing-site"}, "known sites"),
                ("remove_section", {"slug": "kuya", "section_id": "ghost"}, "no section with id"),
                (
                    "render_site",
                    {"payload": {"meta": {"title": "Evil"}, "sections": [
                        {"type": "resources", "title": "R", "groups": [
                            {"label": "L", "items": [{"title": "x", "url": "javascript:alert(1)"}]}]}]}},
                    "not allowed",
                ),
            ]:
                result = await session.call_tool(tool, arguments)
                message = _text(result)
                _check(
                    bool(result.is_error) and needle in message,
                    f"{tool} error mentions {needle!r}: {message.splitlines()[0][:90]}",
                )

    print("\nall checks passed")
    print(f"data dir: {env['SPONGEBOB_DATA_DIR']}")


if __name__ == "__main__":
    asyncio.run(main())
