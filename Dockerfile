FROM node:22-slim AS ui-build
WORKDIR /ui
COPY dev-ui/package.json dev-ui/package-lock.json* ./
RUN npm install
COPY dev-ui/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# uv instead of a separately-maintained requirements.txt - installs straight
# from the committed uv.lock, so the image can never drift from what's
# actually pinned/tested locally.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY configs ./configs

RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=ui-build /ui/dist ./dev-ui/dist

# data/ is a volume in docker-compose.yml, not baked into the image.
VOLUME ["/app/data"]

EXPOSE 8000

# Reports unhealthy (non-2xx) whenever Ollama itself isn't reachable, not
# just when this process is up - see api/routes/health.py.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# This container talks to Ollama running on the host (or a separate
# container) - see docker-compose.yml / OLLAMA_HOST.
CMD ["uvicorn", "roleplay_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
