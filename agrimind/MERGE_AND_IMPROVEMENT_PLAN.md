# AGRIMIND — Smart Merge (V2 → Original) & Remaining Improvement Plan

**Date:** 2026-08-07  
**Target repo:** `AGRIMIND/agrimind` only (V2 not modified as source of truth)  
**Status after merge:** Critical path is **correctly structured** and unit-tested; production AI capabilities still incomplete.

---

## 1. What was merged / fixed (this change set)

### Kernel unification (was BUG-11 / dual package)
- **Single package:** `packages/agrimind-kernel` (`import agrimind_kernel`)
- Removed workspace collision by moving old `packages/kernel` → `packages/_legacy_kernel_removed`
- Merged best of both:
  - Plan-aligned **Query** (UUID, `lang`, modality, geo)
  - Provenance **Citation** (`url_or_path`, `checksum`, excerpt)
  - Full **SafetyLevel** set + default **banned chemicals**
  - **SafetyEngine** on request path (confidence, citations, dosage, injection)
  - **PII redactor**, **rate limiter**, telemetry `TraceContext`, local-safe settings

### Agents package (was missing)
- `packages/agents` with bounded pipeline:
  - intent → retrieval → tools → generate → **safety** → finalize
- Honest simulation labels (`sim-model`, stub feeds)
- No more unsafe high-confidence empty mock

### Correct service flow
```
Farmer → gateway (rate limit + X-Request-ID + proxy)
      → assistant-api (PII redact + HTTP to orchestrator)
      → agent-orchestrator (/v1/run + SafetyEngine)
      → memory HybridRetriever (deterministic stub index)
      → Response with citations / safe fallback
```
- **inference-service** is model boundary only (`/v1/generate`, simulated)
- **expert-console-api** is review queue APIs (not fake `/ask`)
- **admin-service** kill-switch / source allow-list skeleton
- Canonical ports: 8000–8010

### Tooling
- `uv sync --all-packages` works
- Dockerfiles for critical-path services
- Compose commands fixed (no `app.main`)
- `.env.example` with valid local JWT
- Unit/contract/retrieval tests aligned to unified contracts

### Ported from V2 (ideas / code patterns)
| V2 piece | How used in original |
|---|---|
| Agents graph skeleton | Rewritten cleanly in `packages/agents` |
| Safety on request path | Wired via SafetyEngine + fallback |
| Rate limiter + PII | In kernel + gateway/assistant |
| Service Dockerfiles | Critical path Dockerfiles |
| Port map 8000–8010 | Settings + services |
| Feeds/vision thin APIs | Honest stubs with `simulated` flags |

### Explicitly NOT claimed complete
- Real LLM (vLLM/SGLang)
- Live Neo4j / Qdrant
- Full Temporal ingestion lakehouse
- Self-learning flywheel
- Auth JWT enforcement on every route
- LangGraph library StateGraph (structure ready; sequential runner today)

---

## 2. Current honest completion

| Area | Before merge | After merge |
|---|---|---|
| Workspace install | Failed (dual kernel) | **Works** |
| Critical path flow | Broken / mock | **Correct roles + HTTP** |
| Safety on path | Library only | **Enforced** |
| Agents package | Missing | **Present** |
| Retrieval | Schemas only | **Stub HybridRetriever** |
| Real GraphRAG / LLM | Missing | Still missing |
| Data plane E2E | Missing | Still missing |
| **Overall** | ~10–20% scaffold | **~30–40% foundation** |

`COMPLETION_REPORT.md` remains **invalid** for production claims. Prefer this document.

---

## 3. Remaining gaps & ordered improvement plan

### Phase A — Harden foundation (1–2 weeks)
| ID | Work | Exit criteria |
|---|---|---|
| A1 | Delete or archive `packages/_legacy_kernel_removed` after confirming no imports | No legacy tree |
| A2 | Wire gateway optional JWT verify on `/v1/*` | 401 without token in non-local |
| A3 | Point orchestrator generator at inference-service HTTP `/v1/generate` | **DONE** — `InferenceClient` + `/v1/generate`; local fallback only in local/dev/test |
| A4 | Memory-service client from orchestrator (HTTP) instead of in-process only | **DONE** — `MemoryClient` + `/v1/retrieve`; backends exposed on response metadata |
| A5 | GitHub Actions: lint + `pytest tests/unit` | **DONE** — offline CI green (lint + unit/contract/retrieval) |
| A6 | import-linter rules for layer direction | CI fails on upward imports |

**A3/A4 notes (2026-08-07):**
- Clients: `packages/agents/agents/clients/{memory,inference}_client.py`
- Orchestrator prefers HTTP; on failure in local/dev/test falls back and tags `service_local_fallback` + lower confidence
- Response metadata includes `retrieval_backend` / `generation_backend` (`http` | `local_fallback`)
- Production should set `ENV=production` and `allow_local_fallback=False` path (no silent local RAG/LLM)

**A5 notes (2026-08-08):**
- Workflow: `.github/workflows/ci.yml` — push/PR to `main`/`master`, `ubuntu-latest`, Python 3.12 via `astral-sh/setup-uv@v5` (cache on)
- Lint: `ruff` on `packages/{agrimind-kernel,agents,memory,data_kernel}` + `services` + `tests` (`--ignore RUF012,B017,B008`)
- Test: `pytest tests/unit tests/contract tests/retrieval` with `ENV=test`, stub memory, local object store (no Docker)
- Optional: `.github/workflows/eval-retrieval.yml` (`workflow_dispatch` + weekly) runs `make eval-retrieval`
- Makefile `lint` / `test` targets aligned with CI

### Phase B — Real retrieval (2–4 weeks)
| ID | Work | Exit criteria |
|---|---|---|
| B1 | Qdrant client upsert/search with embeddings | **DONE** — `QdrantStore` + `LocalHashEmbedder` + `backend=live\|auto\|stub`; seed/upsert APIs |
| B2 | Neo4j ontology write/read for Crop–Pest–Practice | **DONE** — multi-hop paths + edge provenance; banned edges filtered |
| B3 | Semantic cache in Redis | **DONE** — exact + cosine-near cache; Redis or in-memory; `trace.cache_hit` |
| B4 | Golden retrieval tests with fixture graph | **DONE** — golden fixtures + offline harness; p95 budget **300ms** |

**B1 notes (2026-08-07):**
- Embedder: `memory.vector.embedder.LocalHashEmbedder` (deterministic, no model download; replace with BGE/E5 later)
- Store: `memory.vector.qdrant_store.QdrantStore` (qdrant-client)
- Seed: `POST /v1/index/seed` + auto-seed on empty collection at memory-service startup
- Upsert: `POST /v1/index/upsert`
- Env: `MEMORY_BACKEND=auto|live|stub`, `QDRANT_URL`, `QDRANT_COLLECTION`, `EMBED_DIM`

**B2 notes (2026-08-07):**
- Graph store: `Neo4jGraphStore` + `InMemoryGraphStore` (tests/offline)
- Seed: Crop/Pest/Practice/Treatment with `source_id`, `checksum`, `is_approved`
- Multi-hop: e.g. `Cotton -[AFFECTED_BY]-> Bollworm -[MANAGED_BY]-> IPM`
- Banned monocrotophos edges exist but are **never** returned as approved paths
- APIs: `POST /v1/graph/seed`, `POST /v1/graph/query`, hybrid `mode=graph|hybrid|vector`
- Chemical/dosage KG promotion still needs expert gate (Phase E) — only approved edges surface

**B3 notes (2026-08-08):**
- Cache: `memory.retrieval.semantic_cache` — `InMemorySemanticCache` + `RedisSemanticCache` + `build_semantic_cache`
- Match: exact (lang+normalized query hash) then nearest embedding if cosine ≥ threshold (default 0.92)
- Wired into `HybridRetriever.retrieve()`; hits set `trace.cache_hit=True`, `trace.backend=cache`
- Does not cache empty results or hard errors; factory falls back to in-memory when Redis unreachable
- API: `GET /v1/cache/stats` → hits/misses/size/backend
- Env: `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_TTL_SECONDS`, `SEMANTIC_CACHE_THRESHOLD`, `REDIS_URL`

**B4 notes (2026-08-08):**
- Golden fixtures: `packages/eval/golden/retrieval/*.json` (≥5 cases: cotton bollworm multi-hop, crop rotation, banned chemical exclusion, market/scheme keyword, multilingual aliases)
- Harness: `python -m eval.harness.retrieval_run` / `make eval-retrieval` — offline `InMemoryGraphStore` + fake vector (no Neo4j/Qdrant/Redis)
- **p95 latency budget: 300ms** (plan Phase 5 target for offline fixture path); override with `--budget-ms` or ignore with `--skip-latency`
- Tests: `tests/retrieval/test_golden_retrieval.py`

### Phase C — Data plane (3–5 weeks)
| ID | Work | Exit criteria |
|---|---|---|
| C1 | Connect data-ingestion → Temporal `IngestionWorkflow` | **DONE** — Temporal start + local pipeline fallback; jobs leave `accepted_not_processed` |
| C2 | MinIO raw write + checksum provenance | **DONE** — MinIO or local_fs object store; sha256 provenance |
| C3 | Curation filters: license, PII, relevance, dedup | **DONE** — quarantine on fail |
| C4 | Iceberg/Parquet curated tables | **DONE** — JSONL lakehouse tables + dataset manifests queryable |

**C notes (2026-08-08):**
- Pipeline: `data_kernel.pipeline.ingest_pipeline.IngestPipeline`
- Storage: `build_object_store(prefer=auto|minio|local)` → MinIO when up else `./data/lakehouse`
- Tables: `raw.documents`, `curated.documents`, `quarantine.records`, `manifests.datasets` (JSONL)
- API: `POST /v1/ingest` (`mode=auto|temporal|local`), `GET /v1/jobs/{id}`, `GET /v1/lakehouse/manifests`, `GET /v1/lakehouse/tables/{table}`
- Worker: `curation_worker` Temporal queue `agrimind-ingestion` / `IngestionWorkflow`
- Full Apache Iceberg catalog still future; manifests + JSONL satisfy “queryable curated artifacts”

**Post-C indexing (2026-08-08) — DONE:** curated → Qdrant wired
- Protocol: `data_kernel.pipeline.indexer.ChunkIndexer` (`index_chunks`) — no hard data_kernel→memory dep
- Chunker: `data_kernel.pipeline.chunking.chunk_text` (~800 chars, paragraph-aware, optional overlap)
- Bridge: `memory.indexing.curated_indexer.MemoryChunkIndexer` + `build_default_indexer` (live Qdrant or in-memory fallback)
- `IngestPipeline(indexer=..., index_on_curate=True, index_required=False)` runs after curated write; failures soft by default
- Service/worker attach default indexer when `INDEX_ON_INGEST=true` (default) and memory package available
- Reindex: `POST /v1/index/curated` from lakehouse curated.documents (+ object store body)
- Env: `INDEX_ON_INGEST`, `INDEX_REQUIRED`, `INDEX_PREFER_IN_MEMORY`, `QDRANT_URL`, `QDRANT_COLLECTION`, `EMBED_DIM`
- Tests: `tests/unit/test_curated_index.py` + data_plane recording indexer (offline FakeQdrant)

### Phase 2 — Data Acquisition Plane (pre-stage autonomous data lake) — **DONE (dev-complete)**
| Exit criterion | Status |
|---|---|
| Temporal ingestion workflow runs end-to-end | **DONE** — `IngestionWorkflow` = Ingest → Curation → Index (+ graph); type entry `IngestWebWorkflow` / `IngestPdfWorkflow`; local pipeline when Temporal down |
| Data lake writes immutable objects | **DONE** — MinIO or local_fs; checksum keys; local store refuses overwrite on content mismatch |
| Every record has provenance | **DONE** — `source_id`, checksum, license, source_url on raw/curated/image/quarantine |
| PII redaction passes safety tests | **DONE** — phone/Aadhaar redaction + unit tests |
| Lakehouse manifest queryable | **DONE** — `GET /v1/lakehouse/manifests`, `GET /v1/lakehouse/tables/{table}` |

**Stages 1–13 (implemented):**
1. Source discovery / allow-list (`sources/discovery.py`, `POST /v1/discover`)
2. robots.txt + license (`validators`, `license_filter`)
3. Download size limit + retry + checksum (`pipeline/download.py`)
4. Unicode NFKC + language en/hi/mr (`pipeline/normalize.py`)
5. PII redaction (`pipeline/pii.py`)
6. Toxicity/safety filter (`pipeline/toxicity.py`)
7. Agriculture relevance classifier (`pipeline/relevance.py`)
8. Dedup exact + MinHash near (`pipeline/dedup.py`)
9. Quality scoring (`pipeline/quality.py`)
10. Provenance attachment
11. Raw write (immutable object store)
12. Curated write + chunks table
13. Quarantine on failure

**Source connectors:** web, pdf, wikipedia, rss, json, image, audio, structured (`sources/connectors.py`)

**Lakehouse tables:** `raw.documents`, `curated.documents`, `curated.chunks`, `curated.images`, `quarantine.records`, `manifests.datasets`, `manifests.models`, `telemetry.events`

**Temporal workflows (queue `agrimind-ingestion`):**
- `IngestionWorkflow` (E2E), `IngestWorkflow`, `CurationWorkflow` / `CurationFilterWorkflow`, `IndexWorkflow`, `GraphBuildWorkflow`
- `IngestWebWorkflow`, `IngestPdfWorkflow` (child E2E with source_type)

**Honest gaps remaining (not blocking exit):**
- True Apache Iceberg catalog / Parquet (JSONL stand-in)
- Continuous web crawler beyond allow-list seed catalog
- `graph_build` is seed-ensure, not full NLP entity extraction
- Live Temporal E2E requires running Temporal + worker (offline path uses local pipeline)
- Audio path quarantines pending ASR

**Tests:** `tests/unit/test_phase2_data_acquisition.py`, `tests/unit/test_data_plane.py`, `tests/unit/test_qa_dashboard.py`

### Data Acquisition Console (frontend QA app) — **DONE**
- Path: `frontend/data-acquisition/` (Vite + React + TS)
- Live dashboard: success/quarantine/duplicate %, avg quality, corpus size/records
- Ingest form (all source types) + stage progress checklist
- Tabs: Live Jobs, Ready Corpus, Quality, Quarantine, Duplicates, QA Report (JSON export), Lakehouse
- Backend: CORS + `/v1/qa/*` (dashboard, report, corpus, quality, quarantine, duplicates, demo-batch)
- Start: API `:8007` + `npm run dev` in `frontend/data-acquisition` → http://127.0.0.1:5173
- One-click **Seed QA Demo Batch** for offline full-pipeline evaluation

### Phase D — Models (parallel after B)
| ID | Work | Exit criteria |
|---|---|---|
| D1 | SGLang/vLLM serve one cloud model | **DONE** — OpenAI-compat remote backend when `VLLM_BASE_URL` set; else grounded sim (honest `simulated` flag) |
| D2 | Tokenizer + model manifests gate training | **DONE** — fail-loud tokenizer/dataset/model mismatch gates |
| D3 | Eval harness blocks bad promotions | **DONE** — `evaluate_promotion` + `POST /v1/models/promote` + `eval.harness.promotion_gate` |

**D notes (2026-08-08):**
- Backends: `GroundedSimBackend` | `OpenAICompatBackend` (vLLM/SGLang OpenAI `/v1/chat/completions`)
- Engine: `inference.engine.InferenceEngine` + registry serve gate
- Registry seed: `agrimind-7b-sim-v0.1.0` (promotable), `agrimind-7b-bad-v0.0.1` (blocked)
- Env: `INFERENCE_MODE=auto|sim|remote`, `VLLM_BASE_URL`, `VLLM_API_KEY`, `MODEL_REGISTRY_LOCAL`
- CLI: `uv run python -m eval.harness.promotion_gate --registry ./data/model-registry --model-id agrimind-7b-bad-v0.0.1` → exit 2
- True GPU vLLM weights not bundled; remote path is production-ready client

**GPU vLLM deployment packaging (2026-08-08) — DONE (weights not bundled):**
- `docker-compose.vllm.yml` — profile `gpu`, image `vllm/vllm-openai`, host port **8008→8000**, NVIDIA device reservation
- Docs: `infra/vllm/README.md` (prereqs, wire-up, troubleshooting)
- Optional k8s: `infra/k8s/overlays/gpu/vllm-deployment.yaml` (`nvidia.com/gpu: 1`)
- Smoke: `scripts/smoke_vllm.sh` / `scripts/smoke_vllm.ps1`; Make: `vllm-up` / `vllm-down` / `vllm-smoke`
- Offline unit: `tests/unit/test_vllm_backend.py` (URL + mock httpx; no GPU in CI)
- Start: `docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu up -d vllm`
- Wire: `INFERENCE_MODE=remote` `VLLM_BASE_URL=http://localhost:8008/v1` `VLLM_API_KEY=EMPTY`

### Phase E — Flywheel & expert HITL
| ID | Work | Exit criteria |
|---|---|---|
| E1 | Capture low-confidence + thumbs feedback | **DONE** — JSONL/memory + **Postgres** (`PostgresFeedbackStore`, `FEEDBACK_STORE=auto`); auto low-conf + thumbs APIs |
| E2 | Expert approve chemical/dosage graph nodes | **DONE** — `GatedGraphWriter` + expert-console proposals |
| E3 | Canary + rollback hooks | **DONE** — `CanaryController` + inference `/v1/canary/*` auto-rollback |

**E notes (2026-08-08):**
- Feedback: `agrimind_kernel.feedback` — types thumbs/low_conf/safety_fallback/expert_correction
- Assistant: auto-capture on chat; `POST /v1/feedback`, `GET /v1/feedback/stats`
- Expert: `POST /v1/graph/propose/*`, `POST /v1/graph/proposals/decide`, `GET /v1/feedback`
- High-risk KG (`Chemical`/`Dosage`/`Treatment`, `TREATED_BY`/`HAS_DOSAGE`) stays pending until agronomist approves
- Canary: start → evaluate scores → rollback on regression; traffic split via `choose_model`
- Durable feedback: `PostgresFeedbackStore` (`feedback/postgres_store.py` + `schema.sql`); `FEEDBACK_STORE=auto` tries `POSTGRES_DSN` then falls back to `./data/feedback/events.jsonl`
- Migrate: `uv run python -m agrimind_kernel.feedback.migrate` (or `ensure_schema()`)
- Graph approvals still JSONL: `./data/graph/approvals.jsonl`

### Phase F — Production hardening
| ID | Work | Exit criteria |
|---|---|---|
| F1 | OIDC + tenant RBAC | **DONE** — local HS256 + **live OIDC** (discovery, JWKS cache, code exchange) |
| F2 | Full OTEL instrumentation | **DONE** — OTEL middleware on gateway/assistant/orchestrator; no-op when disabled |
| F3 | Load tests + SLOs | **DONE** — `run_load` + budgets; pytest load asserts p95 |

**F notes (2026-08-08):**
- Auth: `agrimind_kernel.security.auth` — `issue_token`, `decode_token`, `require_roles`, `Principal`
- **OIDC live integration done:** `agrimind_kernel.security.oidc` — `OIDCConfig`, `discover`, `JWKSCache`, `validate_oidc_token` (RS256/ES256, iss/aud/exp); Keycloak `realm_access.roles` + `https://agrimind/tenant` mapping
- Gateway: `POST /v1/auth/token` (local-dev), `GET /v1/auth/me`, `GET /v1/auth/oidc/config`, `GET /v1/auth/oidc/login`, `POST /v1/auth/oidc/token` (code exchange / PKCE); proxies inject `X-Tenant-ID` / `X-User-ID` / `X-Roles`
- Docs: `docs/OIDC.md` (Keycloak + Auth0 + env); tests: `tests/unit/test_oidc.py` (offline RSA mock)
- `AUTH_REQUIRED=false` in local/test; true by default in production/staging
- OTEL: `telemetry/otel.py` — OTLP when packages present; `OTEL_SDK_DISABLED=true` for CI
- SLOs: chat p95 2000ms, retrieval p95 **300ms**, agent_local p95 500ms (`agrimind_kernel.slo`)
- Load: `tests/load/test_load_basic.py` + unit `test_phase_f_hardening.py`

---

## 4. How to run (local)

```bash
cd agrimind
cp .env.example .env
uv sync --all-packages
uv run pytest tests/unit tests/contract tests/retrieval -q

# Critical path (3 terminals)
uv run uvicorn agent_orchestrator.main:app --app-dir services/agent-orchestrator --port 8002
uv run uvicorn assistant_api.main:app --app-dir services/assistant-api --port 8001
uv run uvicorn gateway_service.main:app --app-dir services/gateway-service --port 8000

# Then:
curl -s http://localhost:8000/ask -H "Content-Type: application/json" \
  -d "{\"text\":\"What is crop rotation?\",\"lang\":\"en\",\"user_id\":\"farmer1\"}"
```

Infra only: `docker compose up -d postgres minio neo4j qdrant redis temporal`

---

## 5. Correctness principles applied

1. **Never return high confidence without retrieval + safety**  
2. **Service roles must match plan names** (gateway ≠ orchestrator ≠ inference)  
3. **Stubs must be labeled** (`simulated`, `stub`, `accepted_not_processed`)  
4. **Banned chemicals always block**  
5. **Chemical dosage confidence floor 0.95** — stub cannot pass chemical advice casually  
6. **Single kernel contract** — no dual `Query` shapes  

---

## 6. Recommendation

Continue **only in this original monorepo**. Treat V2 as a completed donor of patterns; do not dual-maintain.

Next PR: **A3 + A4** (orchestrator calls memory + inference over HTTP) then **B1** (live Qdrant).
