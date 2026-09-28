#!/usr/bin/env bash
# Start convertkit. Bound to localhost only.
cd "$(dirname "$0")"
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-8420}" "$@"
