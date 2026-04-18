# Dedalus (Python) — local setup

This folder is a minimal Python setup to verify Dedalus Labs is working and to start the Flux transaction orchestrator.

## 1) Create a virtualenv

```bash
cd orchestrator
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Install deps

```bash
pip install -r requirements.txt
```

## 3) Set environment variables

Use placeholders from `flux/.env` (recommended), or export directly:

```bash
export DEDALUS_API_KEY="dsk-..."
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_KEY="<service-role-key>"
```

## 4) Smoke test Dedalus

```bash
python hello_dedalus.py
```

## 5) Orchestrator

`orchestrator.py` defines `route_transaction(txn)` first, and stubs the specialist tools it will call next:

- `ai_spend_agent`
- `saas_agent`
- `compliance_agent`
- `flag_for_founder`
- `write_alert`

Those are intentionally `NotImplementedError` for now — the goal here is to lock in the orchestrator contract and prompt first.

