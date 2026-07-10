#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" - <<'PY'
import sys

if sys.version_info < (3, 9):
    raise SystemExit(f"Python 3.9+ is required. Found {sys.version.split()[0]}.")
PY

if [ ! -d ".venv" ]; then
    "${PYTHON_BIN}" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r kaohsiung_microclimate_lstm/requirements.txt

mkdir -p \
    data/raw \
    data/processed \
    logs \
    kaohsiung_microclimate_lstm/models \
    kaohsiung_microclimate_lstm/results \
    kaohsiung_microclimate_lstm/data/raw \
    kaohsiung_microclimate_lstm/data/processed

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
fi

echo "Install complete. Start the API with:"
echo "source .venv/bin/activate && uvicorn app.api:app --reload"
