FROM oven/bun:1 AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend ./
# type-checking (vue-tsc) needs Node; the image only bundles
RUN bunx vite build

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install --no-cache-dir .

COPY alembic ./alembic
COPY alembic.ini .
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8723

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8723"]
