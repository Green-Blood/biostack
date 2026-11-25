FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
# config.py finds the project root three levels up, so keep the repository's own layout.
WORKDIR /srv/biostack/apps/api
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/srv/biostack/apps/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
