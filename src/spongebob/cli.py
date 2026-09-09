"""Command line entry points.

``spongebob mcp``    stdio MCP server — this is what an MCP client launches.
``spongebob serve``  standalone static server, so sites outlive the MCP client.
``spongebob render`` render a payload file straight from disk (fast template loop).
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import config, serve, store
from .models import SitePayload
from .render import render_site, render_site_index


def _render(args: argparse.Namespace) -> int:
    path = Path(args.payload)
    if not path.is_file():
        print(f"no such payload file: {path}", file=sys.stderr)
        return 1
    try:
        payload = SitePayload.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as error:  # noqa: BLE001 - surface validation detail verbatim
        print(f"payload is invalid:\n{error}", file=sys.stderr)
        return 1

    if args.slug:
        payload.meta.slug = store.safe_slug(args.slug)

    result = render_site(payload)
    port = serve.ensure_running() if args.open else serve.running_port()
    url = serve.site_url(result.slug, port)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"rendered {len(result.pages)} pages to {result.directory}")
    print(url if port else f"{url}  (start the server with: spongebob serve)")

    if args.open:
        webbrowser.open(url)
    return 0


def _serve(args: argparse.Namespace) -> int:
    render_site_index()
    serve.serve_forever(args.port)
    return 0


def _list(_args: argparse.Namespace) -> int:
    sites = store.list_sites()
    if not sites:
        print("no sites rendered yet")
        return 0
    port = serve.running_port()
    width = max(len(s.slug) for s in sites)
    for site in sites:
        print(
            f"{site.slug.ljust(width)}  {site.section_count:>2} sections  "
            f"{site.card_count:>3} cards  {site.updated_at}  {serve.site_url(site.slug, port)}"
        )
    return 0


def _delete(args: argparse.Namespace) -> int:
    if store.delete_site(args.slug):
        render_site_index()
        print(f"deleted {args.slug}")
        return 0
    print(f"no site named {args.slug}", file=sys.stderr)
    return 1


def _mcp(_args: argparse.Namespace) -> int:
    from .mcp_server import run_stdio

    run_stdio()
    return 0


def _paths(_args: argparse.Namespace) -> int:
    print(f"data dir : {config.data_dir()}")
    print(f"sites    : {config.sites_dir()}")
    print(f"state    : {config.state_file()}")
    port = serve.running_port()
    print(f"server   : {'running on ' + serve.base_url(port) if port else 'not running'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spongebob",
        description="Render agent-authored JSON into a served, multi-page learning site.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    mcp = subparsers.add_parser("mcp", help="run the MCP server over stdio")
    mcp.set_defaults(func=_mcp)

    server = subparsers.add_parser("serve", help="serve rendered sites over HTTP")
    server.add_argument("--port", type=int, default=None, help="port to bind (default $SPONGEBOB_PORT or 8787)")
    server.set_defaults(func=_serve)

    render = subparsers.add_parser("render", help="render a payload JSON file")
    render.add_argument("payload", help="path to a payload JSON file")
    render.add_argument("--slug", default=None, help="override the site slug")
    render.add_argument("--open", action="store_true", help="open the site in a browser")
    render.set_defaults(func=_render)

    listing = subparsers.add_parser("list", help="list rendered sites")
    listing.set_defaults(func=_list)

    delete = subparsers.add_parser("delete", help="delete a rendered site")
    delete.add_argument("slug")
    delete.set_defaults(func=_delete)

    paths = subparsers.add_parser("paths", help="show where spongebob keeps things")
    paths.set_defaults(func=_paths)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
