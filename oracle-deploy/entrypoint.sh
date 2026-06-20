#!/bin/bash
set -e
PORT="${WEB_PORT:-8081}"
exec uvicorn app.server:app --host 0.0.0.0 --port "$PORT"
