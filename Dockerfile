# --- Stage 1: build the React frontend -------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
# The repository root holds the canonical logo; frontend/public/ carries a copy so
# `npm run dev` serves it too. Overwrite it here so the image always ships the root one.
COPY logo.svg ./public/logo.svg
RUN npm run build

# --- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ADGUARDHUB_DATA_DIR=/data \
    ADGUARDHUB_STATIC_DIR=/app/static

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./static

# The DB and its encryption-key-dependent contents live here; mount a volume.
RUN mkdir -p /data && useradd --system --uid 10001 adguardhub && chown -R adguardhub /data /app
USER adguardhub

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
