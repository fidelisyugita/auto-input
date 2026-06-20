# Self-contained build — run from oracle-deploy folder:
#   docker compose up -d --build
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot_core/ /app/bot_core/
COPY bot_worker/browser_setup.py /app/bot_core/browser_setup.py
COPY app/ /app/app/
COPY bot_worker/ /app/bot_worker/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/app/bot_core:/app
ENV DATA_DIR=/data
ENV HEADLESS=true
ENV WEB_PORT=8081

VOLUME /data
EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
