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

# gosu drops privileges in the entrypoint after it has fixed /data's ownership.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data

# The container starts as root only so the entrypoint can chown the mounted /data,
# then re-execs the app as PUID:PGID. Override those to match the host user that
# owns the mount (Unraid: PUID=99, PGID=100).
ENV PUID=1000 \
    PGID=1000

# The release tag, passed by the Release workflow (--build-arg ADGUARDHUB_VERSION=0.2.0).
# Deliberately the last thing that changes between releases: everything above it —
# apt, pip, the frontend build — is identical from one tag to the next and stays
# cached, so cutting a release rebuilds a layer rather than an image. Empty for a
# local build, which then reports "dev" rather than borrowing a release number it
# was not cut from.
ARG ADGUARDHUB_VERSION=""
ENV ADGUARDHUB_VERSION=${ADGUARDHUB_VERSION}

VOLUME ["/data"]

# The container listens on 80; publish it wherever you like (-p 8080:80). Docker
# sets net.ipv4.ip_unprivileged_port_start=0, so the unprivileged app user may bind it.
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:80/api/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
