# Сборка фронтенда
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Сервер: FastAPI раздаёт API и собранный фронтенд
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/
RUN uv sync --project backend --frozen --no-dev
COPY backend/ backend/
COPY certs/ certs/
COPY --from=web /web/dist frontend/dist
ENV WAYLO_DB=/tmp/waylo.sqlite3 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
