FROM python:3.13.0-slim AS base

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Disable core dumps
RUN echo "ulimit -c 0" >> /etc/profile


FROM node:22.14-alpine AS js-deps
WORKDIR /build

# Copy only relevant files to leverage docker cache
COPY orval.config.js package-lock.json package.json postcss.config.mjs tsconfig.json vite.config.js .
COPY ./frontend ./frontend
# Need to copy as well for tailwind classes used in templates to be parsed, can be removed if we move to SPA
COPY ./backend ./backend
# Install application into container
RUN npm install
RUN npm run build


FROM base AS runtime
# Update package lists
RUN apt update
# Install build tools
RUN apt install -y build-essential gcc g++
# Install dependencies
RUN apt install -y libpq-dev libsnappy-dev libcurl4-openssl-dev libssl-dev
RUN apt install -y openssl
# Clean up the apt cache to reduce image size
RUN apt-get clean && rm -rf /var/lib/apt/lists/*
# Install poetry and compilation dependencies
RUN pip install poetry==2.0.1
# Install python dependencies in /.venv
COPY pyproject.toml .
COPY poetry.lock .
ENV POETRY_VIRTUALENVS_IN_PROJECT true
RUN poetry install --without dev --no-interaction

ENV PATH="/.venv/bin:$PATH"

# Create and switch to a new user
WORKDIR app

# Install application into container
COPY . .
COPY --from=js-deps /build/backend/static_built ./backend/static_built

# Collect static files
RUN DJANGO_SETTINGS_MODULE="backend.config.settings.prod" \
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

