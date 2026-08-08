# AGRIMIND — Real Data Source Auto Discovery

## Production paths (use these)

| Role | Path |
|------|------|
| Allow-list, trust, seed catalog, access check | `packages/data_kernel/data_kernel/sources/discovery.py` |
| EN/HI/MR keyword discovery + PDF books | `packages/data_kernel/data_kernel/sources/keyword_discovery_service.py` |
| Category taxonomy discovery | `packages/data_kernel/data_kernel/sources/online_discovery.py` |
| Fetch web/pdf/wiki (HI/MR titles) | `packages/data_kernel/data_kernel/sources/connectors.py` |
| HTTP API (DAQ) | `services/data-ingestion-service/.../main.py` → `/v1/sources/*` |
| CLI | `scripts/discover_agri_sources.py` |
| Batch ingest script | `scripts/run_real_ingest.ps1` |

Plan-folder `*_improved.py` files are **mirrors** that re-export production modules (no forked logic).

## Languages

- **en** — English Wikipedia + FAO/USDA/Archive books  
- **hi** — Hindi Wikipedia + Devanagari keyword expansion (कपास, सिंचाई, …)  
- **mr** — Marathi Wikipedia + keyword expansion (कापूस, सिंचन, …)

## Quick start

```powershell
cd agrimind
# CLI discovery
uv run python scripts/discover_agri_sources.py -k "cotton,soil health" --langs en,hi,mr

# Or via API (service on 8017)
uv run uvicorn data_ingestion_service.main:app --host 127.0.0.1 --port 8017 --app-dir services/data-ingestion-service
```

```powershell
$body = @{
  keywords = @("cotton","soil health")
  languages = @("en","hi","mr")
  check_access = $false
} | ConvertTo-Json
Invoke-RestMethod -Method POST http://127.0.0.1:8017/v1/sources/discover-keywords `
  -ContentType application/json -Body $body
```

```powershell
# Discover then ingest
pwsh scripts/run_real_ingest.ps1 -Port 8017 -DiscoverKeywords "soil health,cotton" -Langs "en,hi,mr"
```

## APIs

| Method | Path |
|--------|------|
| POST | `/v1/sources/discover-keywords` |
| POST | `/v1/sources/discover-online` |
| POST | `/v1/sources/discover-pdf-books?topic=` |
| POST | `/v1/sources/check-access` |
| GET | `/v1/sources/catalog` |
| GET | `/v1/sources/discovery-services` |
| POST | `/v1/ingest/batch` |

Standalone factory (optional):

```bash
uvicorn data_kernel.sources.keyword_discovery_service:create_discovery_app --factory --port 8018
```

## Trusted tiers (summary)

**Tier 1:** ICAR, gov.in, FAO, USDA, CGIAR/IRRI/ICRISAT, Wikipedia, Archive.org, World Bank  
**Tier 2:** PubMed Central, extension, IMD, open journals  

Full domain list: `DEFAULT_ALLOW_LIST` in `discovery.py` (70+).

## Python usage

```python
from data_kernel.sources.keyword_discovery_service import (
    AutoSourceDiscoveryService,
    expand_keywords,
)
from data_kernel.sources.connectors import fetch_source

print(expand_keywords(["cotton"], ["en", "hi", "mr"]))
svc = AutoSourceDiscoveryService(check_access=False)
hits = svc.discover_by_keywords(
    keywords=["cotton", "soil health"],
    languages=["en", "hi", "mr"],
)
fetched = fetch_source(hits[0].source_url, hits[0].source_type)
print(fetched.word_count(), fetched.language_hint)
```

## Security practices

- User-Agent: `AGRIMIND-Bot/1.0`
- Robots.txt respected (cached, fail-open)
- Allow-list suffix matching
- License normalize → pipeline gates
- HEAD before GET; size limits on download
- Agri title filter (blocks off-topic Archive noise)

## Status

See `IMPLEMENTATION_STATUS.md` in this folder.
