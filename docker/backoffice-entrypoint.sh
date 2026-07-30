#!/bin/sh
set -eu

python /app/docker/database-bootstrap.py

exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    'backoffice:create_app()'
