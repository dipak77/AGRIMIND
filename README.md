# AGRIMIND

Autonomous Agricultural Intelligence Engine monorepo.

## Layout

| Path | Purpose |
|---|---|
| [`agrimind/`](./agrimind/) | **Main codebase** (packages, services, workers, tests) |
| [`frontend/`](./frontend/) | UI apps — **Data Acquisition Console** (QA) |
| [`AGRIMIND_Implementation_Plan.md`](./AGRIMIND_Implementation_Plan.md) | Architecture & implementation plan |

## Quick start

```bash
cd agrimind
cp .env.example .env
uv sync --all-packages
uv run pytest tests/unit -q
```

Status and remaining work: [`agrimind/MERGE_AND_IMPROVEMENT_PLAN.md`](./agrimind/MERGE_AND_IMPROVEMENT_PLAN.md)

## Data Acquisition Console (Phase 2 QA)

```powershell
# Terminal 1 — API
cd agrimind
uv run --package data-ingestion-service uvicorn data_ingestion_service.main:app --port 8007

# Terminal 2 — UI
cd ..\frontend\data-acquisition
npm install
npm run dev
```

Open http://127.0.0.1:5173 → **Seed QA Demo Batch** for a full transparent walkthrough.  
Docs: [`frontend/data-acquisition/README.md`](./frontend/data-acquisition/README.md)
