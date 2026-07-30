FROM python:3.12-slim

WORKDIR /app

COPY backoffice/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backoffice ./backoffice

ENV FLASK_APP=backoffice.app
ENV FLASK_ENV=development
ENV PYTHONPATH=/app

EXPOSE 5000

# Use Gunicorn for production-like serving
CMD ["sh", "-c", "flask db upgrade && flask seed && gunicorn --bind 0.0.0.0:5000 --workers 4 backoffice.app:create_app()"]
</write_to_file>