FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backoffice/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt gunicorn

COPY backoffice /app/backoffice
COPY docker/backoffice-entrypoint.sh /app/docker/backoffice-entrypoint.sh
COPY docker/database-bootstrap.py /app/docker/database-bootstrap.py

RUN chmod 0555 /app/docker/backoffice-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/app/docker/backoffice-entrypoint.sh"]
