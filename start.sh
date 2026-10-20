#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
if [ ! -f .env ]; then cp .env.example .env; fi
.venv/bin/python -m alembic upgrade head
printf 'Open http://127.0.0.1:8000\n'
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
