# spongebob in a container.
#
#   podman build -t spongebob -f Containerfile .
#   podman run --rm -p 8787:8787 -v spongebob-sites:/data spongebob
#
# The default command serves whatever sites live in the volume. To use it as an
# MCP server, run `spongebob mcp` with stdio attached instead:
#
#   podman run --rm -i -v spongebob-sites:/data spongebob spongebob mcp
#
FROM docker.io/library/python:3.13-slim

# uv installs the locked dependency set without needing a compiler.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    SPONGEBOB_DATA_DIR=/data \
    SPONGEBOB_HOST=0.0.0.0 \
    SPONGEBOB_PORT=8787

WORKDIR /app

# Dependencies first, so editing the source does not re-resolve the lockfile.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project

COPY src ./src
COPY examples ./examples
COPY NOTICE ./
RUN uv sync --locked

# Sites are persisted here; mount a volume so they survive the container.
VOLUME /data
EXPOSE 8787

# Rendered sites reference their own URL, which the host sees on the mapped
# port. Override when the mapping is not 1:1, e.g.
#   -e SPONGEBOB_PUBLIC_URL=http://localhost:9000
ENV SPONGEBOB_PUBLIC_URL=http://127.0.0.1:8787

ENTRYPOINT []
CMD ["spongebob", "serve"]
