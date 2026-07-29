FROM python:3.12-slim

WORKDIR /app

COPY backoffice/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backoffice ./backoffice

ENV FLASK_APP=backoffice.app
ENV FLASK_ENV=development
ENV PYTHONPATH=/app

EXPOSE 5000

CMD ["sh", "-c", "flask db upgrade && flask seed && flask run --host=0.0.0.0 --port=5000"]