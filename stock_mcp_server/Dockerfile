FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY stock_mcp_server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY stock_mcp_server /app/stock_mcp_server

EXPOSE 8200

CMD ["python", "-m", "stock_mcp_server.server"]
