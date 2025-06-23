# DataRoom

<img src="./screenshot.jpg" alt="Screenshot of DataRoom UI" />

[![Tests](https://github.com/Photoroom/dataroom/actions/workflows/test.yml/badge.svg)](https://github.com/Photoroom/dataroom/actions/workflows/test.yml)

DataRoom is a high-performance AI training data management platform featuring a beautiful UI, multimodal support (images, latents, masks), similarity search, and a Python client for seamless integration.

To try it out, follow the guide below. Also check out the Python client inside [dataroom_client](./dataroom_client) and the examples in [notebooks](./notebooks).

## Getting Started

The simplest and fastest way to get a Dataroom stack up and running is to use Docker. If you prefer to run it without Docker, see section [Setup without Docker](#setup-without-docker).

```
cp .env.example .env
cp backend/config/settings/local.example.py backend/config/settings/local.py
```

```
docker compose up -d --build
```

**Run initial migrations**

```
docker compose run --rm dataroom_django python manage.py migrate
```

**Collect static**

```
docker compose run --rm dataroom_django python manage.py collectstatic --link --clear --noinput
```

**Create admin user**

```
docker compose run --rm dataroom_django python manage.py createsuperuser
```

### Run development server

```
docker compose run --service-ports dataroom_django python manage.py runserver 0.0.0.0:8000
```

### Run production server

```
docker compose run --service-ports dataroom_django ./scripts/run_web.sh
docker compose run --service-ports dataroom_django ./scripts/run_tasks.sh
```

### Run tests

```
docker compose run --rm dataroom_django pytest
```

### Useful commands

```
docker compose exec dataroom_postgres bash -c "su postgres -c 'dropdb dataroom && createdb dataroom'"
```

## Frontend setup

Install the project's version of node defined in `.nvmrc`:

```
nvm install
```

Use the correct version of node:

```
nvm use
```

Install dependencies:

```
npm install
```

## Development setup

Install pre-commit hooks:

```
pre-commit install --hook-type pre-commit
```

## Running

Run the backend with auto-reload:

```
python manage.py runserver
```

Run the frontend with auto-reload:

```
npm run dev
```

Run Tasks:

```
python -m backend.task_runner.run --settings local
```

### Running tests

To run backend tests:

```
pytest
```

### Static files in production

- The entries in `rollupOptions` inside [vite.config.js](./vite.config.js) define which entry points are going to be built.
- Anything inside [/frontend/public/](./frontend/public) will simply be copied over. Use this for images included in the HTML.
- Running `npm run build` builds and bundles the frontend, generating a `manifest.json`.
- Built files are now ready in `/backend/static_built/`.
- Running `python manage.py collectstatic` collects the static files, runs whitenoise, compressing and adding a hash to the filename.
- Final static files are now ready to be served from `/backend/static_collected/`.


## Setup without Docker

<details>
  <summary>If you prefer to run the project on MacOS without Docker, follow these steps.</summary>

### Prerequisites

Install these prerequisites:

- `python@3.13.0`
- `virtualenv` https://virtualenv.pypa.io/en/latest/installation.html
- `poetry@2.0.1` https://python-poetry.org/docs/#installation
- `nvm` https://github.com/nvm-sh/nvm
- Postgres v16 https://postgresapp.com/
- `brew install snappy`

To use homebrew's openssl and snappy, add the following to your `.zshrc`:

```
export LDFLAGS="-L/opt/homebrew/opt/openssl@3/lib -L/opt/homebrew/Cellar/snappy/1.1.10/lib"
export CPPFLAGS="-I/opt/homebrew/opt/openssl@3/include -I/opt/homebrew/Cellar/snappy/1.1.10/include"
```

### Database setup

Create the database:

```
createdb dataroom
```

Run OpenSearch:

```
docker compose up opensearch
```

```
python manage.py setup_opensearch
```

### Backend setup

Use the correct python version from `.python-version`:

```
brew install pyenv
pyenv init
pyenv install
pyenv local
```

To create a virtualenv, inside the root project folder, run:

```
virtualenv .venv
```

To install all python requirements:

```
pip install poetry==1.7.1
poetry install
```

Copy and enable local settings:

```
cp backend/config/settings/local.example.py backend/config/settings/local.py
```

Remember to update the `DATABASES` settings in `backend/config/settings/local.py` to match your local database.

After setting up frontend, build the static files once:

```
npm run build
```

Collect the static files:

```
python manage.py collectstatic --link --clear --noinput
```

</details>
