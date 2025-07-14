#!/bin/bash
set -e

DD_SERVICE=dataroom.tasks DD_DJANGO_INSTRUMENT_MIDDLEWARE=false DD_PROFILING_ENABLED=true DD_APPSEC_ENABLED=false ddtrace-run python -m backend.task_runner.run --settings prod
