# AGRIMIND Data Acquisition Console

Flagship QA console for the **Phase 2 Data Acquisition Plane**.

## What you get

| Tab | Purpose |
|---|---|
| **Command Center** | Live KPIs: success %, quarantine %, duplicate %, avg quality, corpus size |
| **Ingest Source** | Full pipeline submit (web/pdf/wiki/rss/json/image/audio/structured) |
| **Live Jobs** | Real-time job stream with **stage progress %** checklist |
| **Ready Corpus** | Curated docs / chunks / images · size · records · manifests |
| **Data Quality** | High / medium / low tiers, relevance, PII flags |
| **Quarantine** | Reason breakdown + records |
| **Duplicates** | Exact + MinHash near-dup ledger |
| **QA Report** | Checklist score + JSON export for auditors |
| **Lakehouse** | Browse all 8 tables |

## Prerequisites

1. Python services from monorepo (`agrimind/`)
2. Node.js 18+ for the UI

## Start backend (data-ingestion-service)

```powershell
cd C:\Users\haran\source\repos\AGRIMIND\agrimind
uv sync --all-packages
$env:OBJECT_STORE = "local"
$env:LAKEHOUSE_ROOT = "./data/lakehouse"
$env:LAKEHOUSE_TABLE_ROOT = "./data/lakehouse/tables"
$env:INDEX_ON_INGEST = "false"
uv run --package data-ingestion-service uvicorn data_ingestion_service.main:app --host 127.0.0.1 --port 8007 --reload
```

Open API docs: http://127.0.0.1:8007/docs

## Start frontend

```powershell
cd C:\Users\haran\source\repos\AGRIMIND\frontend\data-acquisition
npm install
npm run dev
```

UI: http://127.0.0.1:5173  
Vite proxies `/api` → `http://127.0.0.1:8007`.

Optional env:

```
# frontend/data-acquisition/.env.local
VITE_DAQ_API_BASE=/api
```

## QA walkthrough (recommended)

1. Open UI → click **Seed QA Demo Batch**
2. Watch **Live Jobs** progress to 100% with stage checklist
3. Review **Command Center** percentages
4. Inspect **Ready Corpus**, **Quality**, **Quarantine**, **Duplicates**
5. Generate **QA Report** → **Export JSON** for audit trail

Demo batch includes: good agri text, PII redaction, JSON structured, toxicity block, low relevance, near-duplicate.

## Backend QA APIs

| Method | Path | Description |
|---|---|---|
| GET | `/v1/qa/dashboard` | KPIs + recent jobs + corpus summary |
| GET | `/v1/qa/report` | Full audit report + checklist |
| GET | `/v1/qa/corpus` | Ready corpus details |
| GET | `/v1/qa/quality` | Quality ledger |
| GET | `/v1/qa/quarantine` | Quarantine browser |
| GET | `/v1/qa/duplicates` | Dup ledger |
| POST | `/v1/qa/demo-batch` | Seed offline demo jobs |
| POST | `/v1/ingest` | Run pipeline |
| GET | `/v1/jobs` | Jobs with progress % |
| GET | `/v1/pipeline/stages` | Stage catalog |

## Notes

- Default mode is **local** pipeline (no Temporal required for QA).
- Object store defaults to **local_fs** under `./data/lakehouse`.
- Polling interval is configurable in the top bar (2s–10s).
