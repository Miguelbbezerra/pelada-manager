# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# ---- build: instala as dependências num venv ----
FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# ---- runtime: só o venv + código, rodando sem root ----
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/Miguelbbezerra/pelada-manager"
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --link --from=build --chown=1001:1001 /app/.venv /app/.venv
COPY --link --chown=1001:1001 alembic.ini ./
COPY --link --chown=1001:1001 alembic ./alembic
COPY --link --chown=1001:1001 app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
