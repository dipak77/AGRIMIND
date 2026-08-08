# AGRIMIND Frontend

| App | Path | Port | Purpose |
|---|---|---|---|
| **Data Acquisition Console** | [`data-acquisition/`](./data-acquisition/) | 5173 | Phase 2 lake + QA transparency |

## Quick start — Data Acquisition

```powershell
# Terminal 1 — API
cd ..\agrimind
uv run --package data-ingestion-service uvicorn data_ingestion_service.main:app --port 8007

# Terminal 2 — UI
cd data-acquisition
npm install
npm run dev
```

See [`data-acquisition/README.md`](./data-acquisition/README.md) for the full QA walkthrough.
