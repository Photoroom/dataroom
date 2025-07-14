#!/bin/bash
set -e

# run django checks
#python manage.py check --deploy --fail-level WARNING --settings=backend.config.settings.prod

# migrate database
python manage.py migrate --noinput --settings=backend.config.settings.prod
