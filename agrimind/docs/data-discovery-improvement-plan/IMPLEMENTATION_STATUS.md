# Data Discovery Improvement Plan — Implementation Status

**Plan folder:** `agrimind/docs/data-discovery-improvement-plan/`  
**Date integrated:** 2026-08-08  
**Languages:** English (`en`), Hindi (`hi`), Marathi (`mr`)

## Review summary (plan vs production)

| Plan item | Status | Production location |
|-----------|--------|---------------------|
| Expand allow-list (60+ domains) | **Done** | `packages/data_kernel/data_kernel/sources/discovery.py` |
| Trust scoring + provider/license inference | **Done** | same |
| Access check (HEAD/GET + robots) | **Done** | `check_url_access_sync`, `/v1/sources/check-access` |
| Seed catalog EN + HI + MR + FAO/USDA/ICAR/Archive | **Done** | `default_seed_catalog()` (~30 sources) |
| Keyword expansion EN/HI/MR | **Done** | `keyword_discovery_service.expand_keywords` |
| Live search: Wikipedia / Archive / OL / FAO | **Done** | `keyword_discovery_service` + existing `online_discovery` |
| PDF book finder | **Done** | `find_pdf_books` + `POST /v1/sources/discover-pdf-books` |
| Connectors: PDF 120 pages, HI/MR wiki, word_count | **Done** | `connectors.py` |
| License normalize for pipeline | **Done** | `normalize_license` + `license_filter` |
| FastAPI on data-ingestion-service | **Done** | not separate port — integrated under `/v1/sources/*` |
| UI languages EN/HI/MR | **Done** | DAQ **Discover Sources** tab |

## Production APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/sources/discovery-services` | Services + categories + keyword topics + languages |
| POST | `/v1/sources/discover-keywords` | **Primary** multilingual EN/HI/MR discovery |
| POST | `/v1/sources/discover-online` | Category taxonomy discovery |
| POST | `/v1/sources/discover-pdf-books?topic=` | Agri PDF books |
| POST | `/v1/sources/check-access` | Single URL trust/access report |
| GET | `/v1/sources/catalog` | Seed catalog |
| POST | `/v1/ingest/batch` | Parallel ingest of ready sources |

## How to run

```powershell
cd agrimind
$env:OBJECT_STORE="local"
$env:SKIP_ROBOTS="true"
uv run uvicorn data_ingestion_service.main:app --host 127.0.0.1 --port 8017 --app-dir services/data-ingestion-service
```

```powershell
# Multilingual discovery
$body = @{
  keywords = @("cotton","soil health","irrigation")
  languages = @("en","hi","mr")
  check_access = $false
  max_results = 30
} | ConvertTo-Json
Invoke-RestMethod -Method POST http://127.0.0.1:8017/v1/sources/discover-keywords `
  -ContentType application/json -Body $body
```

## Keyword map examples

| Topic | EN | HI | MR |
|-------|----|----|-----|
| cotton | cotton, cotton farming | कपास | कापूस |
| soil health | soil fertility | मिट्टी की सेहत | माती आरोग्य |
| irrigation | drip irrigation | सिंचाई | सिंचन / ठिबक सिंचन |
| organic | organic farming | जैविक खेती | सेंद्रिय शेती |

## Files (reference plan → production)

| Plan draft | Production module | Sync model |
|------------|-------------------|------------|
| `discovery_improved.py` | `packages/.../sources/discovery.py` | **Re-exports** production (no fork) |
| `keyword_discovery_service.py` | `packages/.../sources/keyword_discovery_service.py` | **Re-exports** production |
| `connectors_improved.py` | `packages/.../sources/connectors.py` | **Re-exports** production |
| `SOURCE_DISCOVERY_GUIDE.md` | updated paths + CLI | Living guide |
| — | `scripts/discover_agri_sources.py` | New CLI |
| — | `scripts/run_real_ingest.ps1 -DiscoverKeywords` | Discover→ingest |

**Rule:** edit production packages only; plan `*_improved.py` files re-export so samples stay valid.

## Tests

```powershell
cd agrimind
uv run pytest tests/unit/test_keyword_discovery_ml.py tests/unit/test_online_discovery.py tests/unit/test_phase2_data_acquisition.py -q
```

## Notes / follow-ups

1. Prefer **stdlib urllib** (no httpx required) for access checks and search adapters.
2. Wikipedia HI/MR search uses Devanagari keywords; Archive/OL PDF search stays EN (book corpus quality).
3. License tags from discovery are normalized to pipeline forms (`cc-by`, `government_open`, `cc0`).
4. Separate FastAPI factory on port 8007 from the plan was **not** deployed as a second service — everything is on **data-ingestion-service** for a single DAQ process.
