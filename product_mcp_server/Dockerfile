FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY product_mcp_server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY product_mcp_server /app/product_mcp_server

EXPOSE 8100

CMD ["python", "-m", "product_mcp_server.server"]
