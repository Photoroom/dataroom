#!/bin/bash
set -e

DD_SERVICE=dataroom.deepscatter DD_DJANGO_INSTRUMENT_MIDDLEWARE=false DD_PROFILING_ENABLED=true DD_APPSEC_ENABLED=false ddtrace-run python -m backend.deepscatter.run
