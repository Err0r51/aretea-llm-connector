# uv multi-stage build (docs.astral.sh/uv/guides/integration/docker).
# Stage 1: resolve + install deps into a venv.
# NOTE: plain COPY (no `RUN --mount=...`). Railway's Metal builder rejects ALL RUN mount types
# (cache AND bind: "other mount types are not supported"), so the usual uv bind-mount pattern
# won't build there. COPYing the lockfiles first still gives dep-layer caching.
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install deps first (this layer is cached unless the lockfiles change), then the project.
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . /app
RUN uv sync --frozen --no-dev

# Stage 2: slim runtime image with just the venv + source.
FROM python:3.12-slim-trixie

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Railway injects $PORT at runtime; shell form is required so it expands.
# init_db creates the FileTreeStore dir on the mounted volume (absent at build time),
# then uvicorn serves the FastMCP http_app directly (single worker: in-memory sessions + one volume).
# NOTE: Railway volumes mount as root; this container runs as root (acceptable for a single-tenant
# internal service — the real boundaries are SA drive membership + the identity gate). To drop
# privileges, add a chown-then-gosu entrypoint (see docs/RUNBOOK).
CMD ["sh", "-c", "python -m aretea_drive_mcp.init_db && exec uvicorn aretea_drive_mcp.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
