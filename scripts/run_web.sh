#!/bin/bash
set -e

DD_SERVICE=dataroom DD_DJANGO_INSTRUMENT_MIDDLEWARE=true DD_PROFILING_ENABLED=true DD_APPSEC_ENABLED=false DD_TRACE_IGNORE_URLS=/_health/ ddtrace-run gunicorn backend.config.wsgi --workers ${NUM_GUNICORN_WORKERS:-2} $( [[ "$DJANGO_DEBUG" = "True" ]] && printf %s '--reload') --timeout 120 --bind 0.0.0.0:8000 --max-requests 1000 --max-requests-jitter 50 --backlog 0 -k gevent --reuse-port --worker-connections=5

# Tip: to debug slow imports, run `ddtrace-run python -X importtime -m gunicorn backend.config.wsgi --workers [etc]``
