FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
WORKDIR /project
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app

FROM base AS test
RUN uv sync --frozen
COPY tests ./tests
RUN uv run pytest --cov -q

FROM base AS runtime
RUN uv sync --frozen --no-dev
ENTRYPOINT ["uv", "run", "reaction-aggregator"]
