#!/bin/bash
set -e

# Set default environment to prod if not specified
ENV=${1:-prod}

# Validate environment
if [ "$ENV" != "dev" ] && [ "$ENV" != "staging" ] && [ "$ENV" != "prod" ]; then
    echo "Error: Invalid environment '$ENV'. Must be 'dev', 'staging', or 'prod'"
    exit 1
fi

echo "Running migrations for $ENV environment..."

# Set environment-specific Django settings
case $ENV in
    "prod")
        DJANGO_SETTINGS="backend.config.settings.prod"
        ;;
    "dev")
        DJANGO_SETTINGS="backend.config.settings.dev"
        ;;
    "staging")
        DJANGO_SETTINGS="backend.config.settings.staging"
        ;;
esac

# run django checks
#python manage.py check --deploy --fail-level WARNING --settings=$DJANGO_SETTINGS

# migrate database
python manage.py migrate --noinput --settings=$DJANGO_SETTINGS

# setup / update opensearch index and mappings
python manage.py setup_opensearch --confirm --settings=$DJANGO_SETTINGS
