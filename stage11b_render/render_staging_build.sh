#!/usr/bin/env bash
set -euo pipefail

# Install application requirements when present, then the Stage 10D Linux stack.
if [[ -f requirements.txt ]]; then
    python -m pip install -r requirements.txt
fi
python -m pip install -r deployment_stage10d/requirements-production.txt
python manage.py check --settings=config.settings_render_staging
python manage.py collectstatic --noinput --settings=config.settings_render_staging
