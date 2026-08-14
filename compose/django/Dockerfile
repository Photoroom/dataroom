FROM python:3.13.0-slim AS base

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random


# ── JS build stage ────────────────────────────────────────────────────────────
FROM node:22.14-alpine AS js-deps
WORKDIR /build

COPY package-lock.json package.json .
RUN npm install

# Copy only relevant files to leverage docker cache
COPY orval.config.js package-lock.json package.json postcss.config.mjs tsconfig.json vite.config.js .
COPY ./frontend ./frontend
# Need to copy as well for tailwind classes used in templates to be parsed, can be removed if we move to SPA
COPY ./backend ./backend

ARG GIT_COMMIT=dev
ENV GIT_COMMIT=$GIT_COMMIT

ARG GIT_REPO_URL=https://github.com
ENV GIT_REPO_URL=$GIT_REPO_URL

RUN echo "[git-info] Building with GIT_COMMIT=${GIT_COMMIT} GIT_REPO_URL=${GIT_REPO_URL}"
RUN NODE_ENV=production npm run build


# ── Python dependency builder (has compilers, stays out of final image) ───────
FROM base AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    libpq-dev libsnappy-dev libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# uv is the fast resolver/installer. Pinned for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /bin/

WORKDIR /build
COPY pyproject.toml uv.lock ./

# Build the virtualenv at /build/.venv straight from uv.lock (no re-resolution).
# uv installs wheels in parallel and reuses downloads across builds via the
# BuildKit cache mount — that's the speedup. We install main + `test` only:
# `test` keeps pytest available for `docker compose run dataroom_django pytest`,
# while `--no-default-groups` drops `dev` (lint tooling) and `develop` (Jupyter).
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/build/.venv \
    UV_PYTHON_DOWNLOADS=never
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group test


# ── Runtime image (no compilers, no dev headers, no poetry) ──────────────────
FROM base AS runtime

# Only runtime libs — no -dev packages, no compilers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libsnappy1v5 libcurl4 openssl curl \
    && rm -rf /var/lib/apt/lists/*

# Disable core dumps
RUN echo "ulimit -c 0" >> /etc/profile

# Copy the pre-built virtualenv from builder (no build tools needed here)
COPY --from=python-builder /build/.venv /.venv
# Fix shebangs in entry point scripts: the builder used /build/.venv but we install at /.venv
RUN find /.venv/bin -maxdepth 1 -type f | xargs grep -Il '' | xargs sed -i 's|^#!.*/bin/python|#!/.venv/bin/python|'
ENV PATH="/.venv/bin:$PATH"

WORKDIR /app

# Install application into container (explicit copies keep frontend source out of the final image)
COPY manage.py ./
COPY scripts/ ./scripts/
COPY models/ ./models/
COPY backend/ ./backend/
COPY --from=js-deps /build/backend/static_built ./backend/static_built

# Collect static files
RUN DJANGO_SETTINGS_MODULE="backend.config.settings.production" \
    DJANGO_ALLOWED_HOSTS="*" \
    DJANGO_SECRET_KEY="tmp" \
    DATABASE_URL="" \
    AWS_S3_ACCESS_KEY_ID="" \
    AWS_S3_SECRET_ACCESS_KEY="" \
    AWS_S3_REGION_NAME="" \
    AWS_STORAGE_BUCKET_NAME="" \
    AWS_CLOUDFRONT_KEY_ID="" \
    AWS_CLOUDFRONT_KEY="" \
    GOOGLE_OAUTH_CLIENT_ID="" \
    GOOGLE_OAUTH_CLIENT_SECRET="" \
    CLOUDFLARE_R2_ENDPOINT_URL="" \
    CLOUDFLARE_S3_ACCESS_KEY_ID="" \
    CLOUDFLARE_S3_SECRET_ACCESS_KEY="" \
    CLOUDFLARE_R2_BUCKET_NAME="" \
    CLOUDFLARE_R2_REGION_NAME="" \
    OPENSEARCH_IMAGES_INDEX_NAME="" \
    AWS_OPEN_SEARCH_URL="http://localhost:9200" \
    AWS_OPEN_SEARCH_ACCESS_KEY_ID="" \
    AWS_OPEN_SEARCH_SECRET_ACCESS_KEY="" \
    AWS_OPEN_SEARCH_REGION_NAME="" \
    IS_BUILD_PROCESS="true" \
    python ./manage.py collectstatic --clear --noinput
