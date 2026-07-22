# Build from the REPO ROOT (compose sets context: .) so the editable
# mission3-shared path dependency (../shared) resolves inside the image.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY shared /app/shared
WORKDIR /app/backend

# Dependency layer first — invalidated only when the lockfile changes
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
RUN uv sync --frozen --no-dev

EXPOSE 8080
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
