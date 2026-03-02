#!/bin/bash
set -e
cd "$(dirname "$0")/.."
. .venv/bin/activate

# Load project environment variables for DB/broker health checks.
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

echo "Newton API server starting on http://127.0.0.1:8000"
echo "Health panel: http://127.0.0.1:8000/"

exec uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
