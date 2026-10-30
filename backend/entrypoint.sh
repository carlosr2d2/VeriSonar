#!/bin/sh
set -e
echo "VeriSonar: aplicando migraciones Alembic"
alembic upgrade head
echo "VeriSonar: API lista"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
