#!/bin/bash
set -a
source ../flux/.env
set +a
source .venv/bin/activate
uvicorn main:app --reload --port 8000
