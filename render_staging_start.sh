#!/usr/bin/env bash
set -euo pipefail
: "${PORT:=10000}"
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --access-logfile - --error-logfile -
