# AGRIMIND — From-Scratch Implementation Plan
## Autonomous Agricultural Intelligence Engine

**Document Type:** Principal AI Systems Architecture & Implementation Plan  
**Architecture Level:** Flagship / Production / 2026 Cutting-Edge AI Platform  
**Target Domain:** Agri-Tech AI  
**Languages:** English, Hindi, Marathi  
**Primary Goal:** Build an autonomous, self-learning, self-improving, production-grade agricultural intelligence platform with a defensible AI moat.

| Field | Value |
|---|---|
| **Revision** | 2026-08-08 — DAQ as-built + **full infra / repository map** |
| **Status** | Living plan (architecture + implemented paths) |
| **Related** | `agrimind/infra/`, `agrimind/docs/`, `frontend/data-acquisition/`, `env/` |

### Revision history (recent)

| Date | Summary |
|---|---|
| 2026-08-08b | **Infra restored in plan**: k8s/observability/vLLM maps, full repo tree with use-comments, deploy/runtime flow graphs (§8, §27) |
| 2026-08-08 | Phase 2 DAQ: demo vs **real** mode, `run_id` lakehouse, EN/HI/MR discovery, failure reports, cleanup, Windows start scripts |
| (prior) | Baseline flagship architecture plan (phases 0–7, flywheel, eval gates) |

> **Why infrastructure looked “missed”:** the previous plan revision focused on the **Data Acquisition Plane** (§26). Infra already exists under `agrimind/infra/` (K8s, Prometheus/Grafana/Loki/OTEL, vLLM) and `docker-compose*.yml`, but was only a one-line stub in §8. This revision documents it fully.

---

### 1. Executive Vision

**AGRIMIND is not a chatbot. It is a self-improving agricultural intelligence engine** that continuously learns from data, farmer interactions, expert corrections, agronomy knowledge graphs, weather feeds, market feeds, satellite signals, and field feedback.

The platform must achieve:

- High-accuracy agricultural reasoning in English, Hindi, and Marathi
- Offline-capable edge intelligence using a small flagship model, e.g., an 18M-parameter rural-first model
- Cloud-scale deep reasoning using a larger MoE model
- GraphRAG-powered factual grounding to reduce hallucination
- Autonomous data acquisition and curation using a production-grade data lake pipeline
- Self-learning flywheel that detects low accuracy, fills knowledge gaps, generates corrective training data, evaluates itself, and safely promotes improvements
- Clean microservice architecture with strict boundaries, test-driven delivery, and production observability
- Flagship-quality safety and trust: no unsafe pesticide advice, no hallucinated dosage, no PII leakage, and full citation/provenance

---

### 2. Non-Negotiable Architectural Principles

#### 2.1 Product Principles

| Principle | Meaning |
|---|---|
| **Farmer safety first** | The system must never hallucinate chemical dosage, treatment, or legal advice |
| **Local language first** | Marathi and Hindi are first-class citizens, not translations added later |
| **Offline-first** | Rural connectivity is unstable; edge inference must work with degraded internet |
| **Explainable answers** | Every important answer must include citations, sources, or confidence metadata |
| **Continuous learning** | The platform must learn from feedback, failures, and expert corrections |
| **Human-in-the-loop** | Autonomous learning is allowed, but unsafe changes require human approval |

#### 2.2 Engineering Principles

| Principle | Meaning |
|---|---|
| **Strict layering** | Kernel, memory, agents, services, pipelines must not form import cycles |
| **Contract-first** | All services communicate through typed contracts |
| **Fail loud** | Missing tokenizer, missing checkpoint, missing config, or bad schema must fail immediately |
| **Deterministic rebuild** | Data, model, and deployment artifacts must be reproducible |
| **Test-driven AI** | Evaluation harnesses are written before model/agent features are considered complete |
| **Observability by default** | Every request, retrieval step, tool call, model call, and failure must be traced |

#### 2.3 AI Principles

| Principle | Meaning |
|---|---|
| **Grounded generation** | Answers must be based on retrieved evidence, knowledge graph facts, or approved tools |
| **Epistemic awareness** | The system must know when it is uncertain and must refuse unsafe guessing |
| **Data-centric improvement** | Accuracy problems are treated as data, retrieval, graph, prompt, tool, or model gaps |
| **Eval-gated deployment** | No model or prompt change goes to production without passing golden evaluations |
| **Safe autonomy** | The system may propose improvements automatically but must not deploy unsafe changes without gates |

---

### 3. Target Product Capabilities

#### 3.1 Farmer-Facing Capabilities

- Multilingual agricultural question answering (En/Hi/Mr)
- Crop disease diagnosis from text and images
- Pest and disease treatment recommendations with safety warnings
- Fertilizer and irrigation guidance
- Weather-aware advisory
- Market price guidance
- Government scheme guidance
- Soil and satellite-based advisory, where available
- Voice-first interaction for low-literacy users
- Offline / low-bandwidth mode

#### 3.2 System-Facing Capabilities

- Autonomous data ingestion from approved sources (**demo vs real** isolation)
- **Keyword discovery EN/HI/MR** over Wikipedia, FAO, Archive, Open Library, India/US gov portals
- PDF, web, RSS, Wikipedia, JSON, image, audio, and structured dataset processing
- **run_id-scoped process folders** with stage logs, job snapshots, partial corpus, failure reports
- PII redaction
- License and source governance (allow-list + trust scoring)
- Duplicate detection
- Language filtering
- Agriculture relevance scoring
- Toxicity filter (agri-aware; crop terms like oilseed rape not false-blocked)
- Knowledge graph construction
- Vector retrieval construction
- Synthetic training data generation
- Model evaluation, fine-tuning, canary deployment, automatic rollback
- Expert review console
- **DAQ operator UI** + cleanup/reset for disk hygiene

---

### 4. 2026 Cutting-Edge Target Architecture

#### 4.1 High-Level Architecture

```mermaid
flowchart TD
    Farmer -->|Voice/Text/Image| Gateway[gateway-service]
    Gateway --> API[assistant-api]
    API --> Orch[agent-orchestrator - LangGraph]
    Orch --> Intent{Intent Router}
    Intent --> Memory[memory-service - GraphRAG + Qdrant]
    Intent --> Vision[vision-service]
    Intent --> Feeds[feeds-service - Weather/Market/Satellite]
    Intent --> Inference[inference-service - SGLang/vLLM]
    Memory --> Neo4j[(Neo4j / FalkorDB)]
    Memory --> Qdrant[(Qdrant)]
    Orch --> Safety[Safety Engine]
    Safety --> Response[Final Response + Citations]
    Response --> Telemetry[telemetry-collector]
    subgraph Data Plane
        Ingestion[data-ingestion-service] --> Curation[curation-worker - Temporal]
        Curation --> Lakehouse[(MinIO/S3 + Iceberg)]
        Lakehouse --> Knowledge[Knowledge Graph Builder]
        Lakehouse --> Training[training-orchestrator]
    end
    subgraph Flywheel
        Eval[eval-service] --> SelfReview[Self-Review Engine]
        SelfReview --> Expert[expert-console-api]
        Expert --> Lakehouse
    end
```

**Flow:** Farmer Query → Gateway (Auth, RateLimit, RequestID) → Assistant API → Agent Orchestrator → [Intent Detection → Retrieval (Graph+Vector+API) → Tool Calls → Inference] → Safety Check → Response with Citations → Telemetry.

### 5. Layered System Architecture

#### 5.1 Strict Layer Model

```
Layer 0: kernel (contracts, config, errors, telemetry, zero dependencies)
Layer 1: data-kernel (lakehouse contracts, dataset manifests, tokenizer manifests)
Layer 2: memory (graph, vector, retrieval contracts)
Layer 3: models (inference contracts, model registry)
Layer 4: agents (LangGraph nodes, tools, safety)
Layer 5: services (FastAPI services, workers)
Layer 6: apps (gateway, expert-console, admin)
```

#### 5.2 Import Rules

**Allowed:**
```
kernel <- data-kernel <- memory <- models <- agents <- services <- apps
```

**Forbidden:**
```
services -> kernel is OK
kernel -> services is FORBIDDEN
memory -> agents is FORBIDDEN
agents -> kernel is OK, but agents -> services is FORBIDDEN
Any upward import cycle is FORBIDDEN
```

> These rules must be enforced in CI using `import-linter` or a custom dependency guard.

---

### 6. Clean Microservice Architecture

#### 6.1 Core Services

| Service | Responsibility | Technology |
|---|---|---|
| **gateway-service** | Authentication, rate limiting, routing, request ID | Envoy/Kong/FastAPI edge |
| **assistant-api** | Farmer-facing chat/query endpoints | FastAPI |
| **agent-orchestrator** | LangGraph agent workflows | FastAPI + LangGraph |
| **memory-service** | GraphRAG and vector retrieval | FastAPI + Neo4j + Qdrant |
| **inference-service** | LLM serving | SGLang/vLLM/ONNX |
| **vision-service** | Crop disease image analysis | FastAPI + vision model |
| **feeds-service** | Weather, market, satellite, government feeds | FastAPI + connectors |
| **data-ingestion-service** | Source ingestion API | FastAPI |
| **curation-worker** | Durable ETL/AI curation | Temporal worker |
| **training-orchestrator** | Training/eval/fine-tune orchestration | Ray/Argo/Temporal |
| **eval-service** | Golden set evaluation and regression checks | FastAPI + eval harness |
| **expert-console-api** | Human review, corrections, approvals | FastAPI |
| **admin-service** | Tenant, source, model, and policy administration | FastAPI |
| **telemetry-collector** | Logs, traces, metrics, eval events | OpenTelemetry collector |

#### 6.2 Data Stores

| Store | Purpose |
|---|---|
| **PostgreSQL** | Transactional metadata, catalog, jobs, eval results |
| **MinIO/S3** | Raw and curated objects, model artifacts, datasets |
| **Apache Iceberg/Parquet** | Lakehouse training tables |
| **DuckDB/Polars** | Analytical queries over lakehouse |
| **Neo4j or FalkorDB** | Knowledge graph |
| **Qdrant** | Vector embeddings |
| **Redis** | Semantic cache, session state, rate limits |
| **Artifact Registry** | Docker images and model packages |

---

### 7. Recommended 2026 Technology Stack

#### 7.1 Core Backend

| Area | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | uv workspace |
| API framework | FastAPI |
| Validation | Pydantic v2 |
| Settings | pydantic-settings |
| Async HTTP | httpx |
| Logging | structlog |
| Tracing | OpenTelemetry |
| Metrics | Prometheus |
| Dashboards | Grafana |
| Lint/format | ruff |
| Type checking | mypy |
| Testing | pytest |

#### 7.2 AI Stack

| Area | Choice |
|---|---|
| Agent orchestration | LangGraph or equivalent bounded state graph |
| Vector embeddings | multilingual BGE / Multilingual E5 |
| Vector DB | Qdrant |
| Graph DB | Neo4j or FalkorDB |
| GraphRAG | ontology-based graph traversal + community summaries |
| Inference cloud | SGLang or vLLM |
| Edge inference | ONNX Runtime / MLC-LLM / TensorRT |
| Training | PyTorch, FSDP, Ray, LoRA/QLoRA, DPO |
| Experiment tracking | MLflow |
| Model registry | immutable model manifests + artifact registry |

#### 7.3 Data Pipeline

| Area | Choice |
|---|---|
| Workflow orchestration | Temporal |
| Object storage | MinIO/S3 |
| Lakehouse | Iceberg/Parquet |
| Query engine | DuckDB/Polars |
| Metadata catalog | PostgreSQL |
| Data contracts | Pydantic + JSON Schema |
| Data quality | Great Expectations or custom Pydantic validators |

---

### 8. Repository Layout (as-built) — structure + short “use” comments

> **Legend:** each line ends with `# use: …` — why the folder exists and when to touch it.

```text
AGRIMIND/                                   # monorepo root (git)
│
├── AGRIMIND_Implementation_Plan.md         # use: master architecture + as-built status
├── README.md                               # use: top-level onboarding
├── start-daq-backend.bat                   # use: start data-ingestion-service (local/dev env)
├── start-daq-frontend.bat                  # use: start DAQ Vite UI
├── start-daq-all.bat                       # use: open both API + UI windows
├── cleanup-daq-data.bat                    # use: dry-run / delete run folders + legacy lakehouse
│
├── env/                                    # use: Windows env packs for DAQ launchers
│   ├── daq.local.env.bat                   # use: OBJECT_STORE=local, port 8017 (default laptop)
│   ├── daq.dev.env.bat                     # use: OBJECT_STORE=auto (try MinIO)
│   └── README.md                           # use: how to pick env
│
├── frontend/                               # use: operator/web UIs (not Python monorepo)
│   └── data-acquisition/                   # use: Phase-2 DAQ console (discover/ingest/QA)
│       ├── src/                            # use: React app (modes, runs, corpus, reports)
│       ├── vite.config.ts                  # use: proxy /api → 127.0.0.1:8017
│       └── package.json                    # use: npm run dev | build
│
└── agrimind/                               # use: Python uv workspace (packages + services)
    ├── pyproject.toml                      # use: workspace members, shared tooling
    ├── uv.lock                             # use: reproducible Python deps
    ├── Makefile                            # use: sync / lint / test / compose shortcuts
    ├── docker-compose.yml                  # use: local infra — Postgres, MinIO, Neo4j, Qdrant, Redis, Temporal
    ├── docker-compose.vllm.yml             # use: optional GPU vLLM stack for remote inference
    ├── .env.example                        # use: copy to .env; secrets + service URLs
    ├── .github/workflows/                  # use: CI (lint/test/gates)
    ├── ADRs/                               # use: architecture decision records
    │   └── 001-monorepo-layering.md        # use: import layer rules
    │
    ├── data/                               # use: runtime generated data (gitignored bulk)
    │   ├── runs/{run_id}/                  # use: ONE acquisition process (demo|real)
    │   │   ├── meta.json                   # use: run header + stats
    │   │   ├── process.jsonl               # use: stage/job event log
    │   │   ├── jobs/*.json                 # use: job snapshots for restart/audit
    │   │   ├── reports/fail-*.json         # use: partial/failure tracking reports
    │   │   └── lakehouse/{objects,tables}  # use: isolated corpus for that run only
    │   ├── lakehouse/                      # use: legacy shared lake (prefer runs/; cleanup-able)
    │   └── source_cache/                   # use: trusted PDF cache (FAO/wiki books) for real mode
    │
    ├── docs/                               # use: feature design docs
    │   ├── OIDC.md                         # use: auth / IdP integration notes
    │   └── data-discovery-improvement-plan/ # use: discovery design + IMPLEMENTATION_STATUS
    │
    ├── packages/                           # use: reusable libraries (import by layer)
    │   ├── agrimind-kernel/                # use: contracts, settings, safety, OIDC, feedback, telemetry
    │   ├── data_kernel/                    # use: DAQ pipeline + discovery + lakehouse writer
    │   │   └── data_kernel/
    │   │       ├── sources/                # use: allow-list, keyword discovery EN/HI/MR, connectors
    │   │       ├── pipeline/               # use: ingest stages, download, PII, toxicity, quality
    │   │       └── lakehouse/              # use: JSONL tables + object store writes
    │   ├── memory/                         # use: GraphRAG, Qdrant/vector, retrieval, cache
    │   ├── models/                         # use: inference backends, registry, canary gates
    │   ├── agents/                         # use: LangGraph graphs + tool clients
    │   ├── eval/                           # use: golden sets en/hi/mr + harness
    │   └── _legacy_kernel_removed/         # use: archived legacy kernel (do not import)
    │
    ├── services/                           # use: FastAPI microservices (one process each)
    │   ├── gateway-service/                # use: edge auth, rate limit, route to APIs
    │   ├── assistant-api/                  # use: farmer-facing query API
    │   ├── agent-orchestrator/             # use: LangGraph orchestration
    │   ├── memory-service/                 # use: retrieval / graph / seed APIs
    │   ├── inference-service/              # use: LLM/vLLM/local backends
    │   ├── vision-service/                 # use: crop image diagnosis path
    │   ├── feeds-service/                  # use: weather/market/satellite feeds
    │   ├── data-ingestion-service/         # use: DAQ API — ingest, runs, discovery, cleanup, QA
    │   ├── eval-service/                   # use: evaluation APIs
    │   ├── expert-console-api/             # use: expert correction / HITL
    │   └── admin-service/                  # use: admin ops APIs
    │
    ├── workers/                            # use: async/Temporal workers (not HTTP)
    │   ├── curation-worker/                # use: Temporal Ingest/Curation/Index workflows
    │   └── training-orchestrator/          # use: training / flywheel jobs
    │
    ├── scripts/                            # use: operator CLIs (not libraries)
    │   ├── discover_agri_sources.py        # use: EN/HI/MR discovery from shell
    │   ├── run_real_ingest.ps1             # use: catalog/discover → parallel ingest
    │   ├── smoke_vllm.ps1 / .sh            # use: verify vLLM OpenAI endpoint
    │
    ├── infra/                              # use: deploy + observe (not application logic)
    │   ├── k8s/
    │   │   ├── base/                       # use: core Deployments/Services/ConfigMap (Kustomize base)
    │   │   └── overlays/
    │   │       ├── local/                  # use: low-resource patches for laptop/dev cluster
    │   │       ├── prod/                   # use: production kustomization
    │   │       └── gpu/                    # use: vLLM GPU Deployment patch
    │   ├── observability/
    │   │   ├── prometheus.yml              # use: scrape configs for services
    │   │   ├── otel-collector-config.yaml  # use: OTLP → metrics/traces/logs pipeline
    │   │   ├── loki-config.yaml            # use: log aggregation
    │   │   ├── datasources/                # use: Grafana datasource provisioning
    │   │   ├── dashboards/                 # use: system + AI quality Grafana JSONs
    │   │   └── alerts/                     # use: Prometheus alert rules
    │   └── vllm/
    │       └── README.md                   # use: GPU compose / HF model / INFERENCE_MODE=remote
    │
    └── tests/                              # use: pytest suites (TDD gates)
        ├── unit/                           # use: fast pure logic (discovery, runs, safety…)
        ├── contract/                       # use: API schema contracts
        ├── retrieval/                      # use: golden retrieval
        ├── safety/                         # use: adversarial / safety engine
        └── load/                           # use: basic load smoke
```

#### 8.1 Layer → folder flow (what depends on what)

```mermaid
flowchart TB
  subgraph Apps["Apps / UIs"]
    FE[frontend/data-acquisition]
    BAT[start-daq-*.bat / env/]
  end
  subgraph HTTP["services/* HTTP"]
    GW[gateway-service]
    DAQ[data-ingestion-service]
    AST[assistant-api]
    ORCH[agent-orchestrator]
    MEM[memory-service]
    INF[inference-service]
  end
  subgraph Lib["packages/* libraries"]
    K[agrimind-kernel]
    DK[data_kernel]
    M[memory]
    MD[models]
    AG[agents]
    EV[eval]
  end
  subgraph Work["workers/*"]
    CW[curation-worker Temporal]
    TO[training-orchestrator]
  end
  subgraph Infra["infra/* + compose"]
    DC[docker-compose.yml]
    K8S[infra/k8s]
    OBS[infra/observability]
    VLLM[infra/vllm + docker-compose.vllm.yml]
  end
  subgraph Data["data/* runtime"]
    RUNS[runs/run_id]
    CACHE[source_cache]
  end

  BAT --> DAQ
  FE --> DAQ
  FE --> AST
  GW --> AST
  GW --> ORCH
  AST --> ORCH
  ORCH --> MEM
  ORCH --> INF
  ORCH --> AG
  DAQ --> DK
  DAQ --> K
  DK --> K
  M --> K
  MD --> K
  AG --> M
  AG --> MD
  CW --> DK
  TO --> MD
  DAQ --> RUNS
  DAQ --> CACHE
  INF --> VLLM
  K8S --> GW
  K8S --> AST
  K8S --> ORCH
  K8S --> MEM
  K8S --> INF
  DC --> OBS
  HTTP --> OBS
```

#### 8.2 Runtime data flow (DAQ process)

```mermaid
flowchart LR
  Op[Operator] --> UI[DAQ UI]
  UI -->|POST ingest/batch discover| API[data-ingestion-service]
  API -->|create run_id| FS[data/runs/run_id]
  API -->|stages 1-13| Pipe[data_kernel IngestPipeline]
  Pipe -->|raw/curated objects| FS
  Pipe -->|JSONL tables| FS
  API -->|partial corpus / fail report| UI
  API -->|cleanup| FS
```

---

### 9. Local Bootstrap Commands

#### 9.1 Create Project

```bash
mkdir agrimind && cd agrimind
uv init
uv workspace add packages/kernel packages/memory packages/agents
git init && git add . && git commit -m "feat: init agrimind monorepo"
```

#### 9.2 Create Root pyproject.toml

```toml
[project]
name = "agrimind"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv.workspace]
members = ["packages/*", "services/*", "workers/*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true

[tool.pytest.ini_options]
pythonpath = ["."]
```

#### 9.3 Create Makefile

```makefile
.PHONY: sync lint type test up down eval

sync:
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy packages/kernel

test:
	uv run pytest tests/unit -q

up:
	docker compose up -d

down:
	docker compose down -v

eval:
	uv run python -m eval.harness.run --dataset golden/en --threshold 0.9
```

#### 9.4 Create .env.example

```env
ENV=local
POSTGRES_DSN=postgresql://agrimind:agrimind_secret_123@localhost:5432/agrimind
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin_secret
# DAQ object store: local | auto | minio
OBJECT_STORE=local
LAKEHOUSE_ROOT=./data/lakehouse
# Prefer local FS when MinIO down (avoids probe spam)
# DATA_ROOT defaults to parent of LAKEHOUSE_ROOT → data/runs/{run_id}
SKIP_ROBOTS=true
INDEX_ON_INGEST=false
INGEST_WORKERS=4
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agrimind123
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
TEMPORAL_ADDRESS=localhost:7233
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
MODEL_REGISTRY_PATH=s3://agrimind-models
JWT_SECRET=change-me
OPENWEATHER_API_KEY=
AGMARKNET_API_KEY=
```

---

### 10. Local Infrastructure Docker Compose

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: agrimind
      POSTGRES_PASSWORD: agrimind
      POSTGRES_DB: agrimind
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: [miniodata:/data]

  neo4j:
    image: neo4j:5.21
    environment:
      NEO4J_AUTH: neo4j/agrimind123
      NEO4J_PLUGINS: '["apoc"]'
    ports: ["7474:7474", "7687:7687"]
    volumes: [neo4jdata:/data]

  qdrant:
    image: qdrant/qdrant:v1.11
    ports: ["6333:6333"]
    volumes: [qdrantdata:/qdrant/storage]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  temporal:
    image: temporalio/auto-setup:1.24
    ports: ["7233:7233", "8233:8233"]
    environment:
      DB: sqlite
      DB_FILENAME: /tmp/temporal.db

volumes:
  pgdata:
  miniodata:
  neo4jdata:
  qdrantdata:
```

---

### 11. Phase-Wise Implementation Plan

> Each phase has Objective, Work items, Test-driven validation, Exit criteria. No phase is complete until its exit criteria are met.

#### Phase 0 — Repository, Tooling, and Safety Net

**Objective:** Create a clean, testable, reproducible monorepo foundation.

**Work Items:**
- Initialize uv monorepo
- Add ruff, mypy, pytest, pre-commit
- Add CI pipeline (GitHub Actions)
- Add dependency rules (import-linter)
- Add base Docker Compose
- Add environment configuration
- Add architecture decision records
- Add golden evaluation folder
- Add logging, tracing, and error contracts

**Required Files:** `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`, `packages/kernel/`, `ADRs/`, `tests/`, `.pre-commit-config.yaml`

**Test-Driven Validation:**

| Test | Success Criteria |
|---|---|
| uv sync | Installs all workspace packages reproducibly |
| make lint | Zero ruff errors |
| make type | Zero mypy errors in kernel package |
| pytest tests/unit | All unit tests pass |
| docker compose up -d | Postgres, MinIO, Neo4j, Qdrant, Temporal, Redis become healthy |

**Exit Criteria:** Monorepo builds locally, all infra containers healthy, CI runs lint/type/tests, no package can import outside allowed layers, golden eval folder exists, env config validated by Pydantic.

#### Phase 1 — Kernel Contracts and Configuration

**Objective:** Create the zero-dependency foundation used by all services.

**Core Kernel Modules:**
```
packages/kernel/
├── contracts/query.py
├── contracts/response.py
├── contracts/citation.py
├── contracts/safety.py
├── config/settings.py
├── errors/
└── telemetry/tracing.py
```

**Key Contracts:**

Query Contract:
```python
class Query(BaseModel):
    query_id: UUID
    text: str
    lang: Literal["en","hi","mr"]
    modality: Literal["text","voice","image","multi"]
    location: Optional[GeoPoint]
    user_id: str
    timestamp: datetime
```

Response Contract:
```python
class Citation(BaseModel):
    source_id: str
    source_type: str
    url_or_path: str
    checksum: str
    span: Optional[str]

class Response(BaseModel):
    query_id: UUID
    answer: str
    lang: str
    citations: list[Citation]
    confidence: float
    model_version: str
    trace_id: str
```

**Configuration Requirements:** All configuration must use Pydantic Settings with fail-loud validation.

**Exit Criteria:** All core contracts frozen and typed, no service uses raw `os.getenv`, production config fails fast when secrets missing, Request ID and trace ID middleware tested, kernel package has zero upward dependencies.

#### Phase 2 — Data Acquisition Plane

**Objective:** Build the pre-stage autonomous data lake with **trusted open-source discovery**, **demo/real isolation**, and **run-scoped process visibility**.

**Implementation status (2026-08):** **Largely complete** for local/real ingest path + DAQ UI. Temporal remains optional (`mode=auto` falls back to local pipeline). See **§26** for full as-built detail.

**Data Sources:**

| Source Type | Example | Mode |
|---|---|---|
| Web | ICAR, agri.gov, USDA NRCS, CGIAR portals | **real** only |
| PDF | FAO OA papers, Archive.org agri books, Wikipedia PDF export | **real** |
| Wikipedia | MediaWiki extracts **en / hi / mr** | **real** |
| RSS / JSON | agricultural feeds / open APIs | planned + partial |
| Image / Audio | crop photos / farmer voice | structure ready; ASR later |
| Inline mock | `example.com` samples for QA | **demo** only |

**Hard rule — demo vs real**

| Rule | DEMO | REAL |
|---|---|---|
| `example.com` / inline mock content | Allowed | **Forbidden** |
| Trusted allow-list hosts only | Soft | **Required** |
| Storage root | `data/runs/demo-*` | `data/runs/real-*` |
| QA demo batch API | Yes | Never mixed into real lakehouse |

**Data Pipeline Stages (implemented in `IngestPipeline`):**
```
1. Source Discovery (allow-list check)
2. robots.txt + License validation
3. Download (size limit, retry, checksum; Archive metadata PDF resolve)
4. Unicode Normalization + Language Detection
5. PII Redaction
6. Toxicity/Safety Filter (agri-aware; oilseed rape not blocked)
7. Agriculture Relevance Scoring
8. Deduplication (exact + near - MinHash)
9. Quality Scoring
10. Provenance Attachment (source_id, checksum, license)
11. Raw Write (immutable object + JSONL)
12. Curated Write + chunks table
13. Quarantine on failure
+ Index (optional Qdrant) + Dataset manifest
```

**Keyword discovery (EN / HI / MR) — as-built**

| Component | Path |
|---|---|
| Allow-list + trust + seed catalog | `packages/data_kernel/data_kernel/sources/discovery.py` |
| Multilingual auto-discovery | `packages/data_kernel/data_kernel/sources/keyword_discovery_service.py` |
| Category taxonomy discovery | `packages/data_kernel/data_kernel/sources/online_discovery.py` |
| Connectors (web/pdf/wiki/rss) | `packages/data_kernel/data_kernel/sources/connectors.py` |
| Design notes | `docs/data-discovery-improvement-plan/` |

**Live search adapters:** Wikipedia (en/hi/mr), Open Library, Internet Archive (metadata PDF resolve), FAO curated PDFs, portal seeds (USDA/ICAR/India gov).

**run_id process foundation**

```text
data/runs/{run_id}/
  meta.json              # mode, stats, status
  process.jsonl          # stage/job events
  jobs/{job_id}.json     # job snapshots
  reports/fail-*.json    # failure / partial reports
  lakehouse/
    objects/             # raw + curated blobs
    tables/*.jsonl       # per-run lake tables
```

**Key APIs (`data-ingestion-service`, default port 8017)**

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/ingest` | Single source; `acq_mode=demo\|real`, optional `run_id` |
| POST | `/v1/ingest/batch` | Parallel catalog/real batch under one `run_id` |
| POST | `/v1/qa/demo-batch` | Isolated demo mocks only |
| GET | `/v1/runs`, `/v1/runs/{id}` | Process folder + job stream |
| GET | `/v1/runs/{id}/corpus` | **Partial** curated corpus for run |
| GET | `/v1/runs/{id}/report` | Failure + partial success tracking report |
| POST | `/v1/admin/cleanup` | Dry-run / delete runs + legacy lakehouse |
| POST | `/v1/sources/discover-keywords` | EN/HI/MR keyword discovery |
| POST | `/v1/sources/discover-online` | Category-based online discovery |

**DAQ frontend:** `frontend/data-acquisition/` (Vite) — Command Center, Discover, Live Jobs, Corpus, QA Report; **REAL/DEMO** toggle; cleanup preview/reset.

**Ops scripts (Windows):**

```bat
start-daq-backend.bat local   # API :8017
start-daq-frontend.bat local  # UI  :5173
start-daq-all.bat local
cleanup-daq-data.bat preview real
cleanup-daq-data.bat delete real
```

**Temporal Workflow Design (optional path):**
```
IngestionWorkflow -> CurationWorkflow -> IndexWorkflow
- local IngestPipeline is default when Temporal unavailable
```

**Lakehouse Tables:** `raw.documents`, `curated.documents`, `curated.chunks`, `curated.images`, `quarantine.records`, `manifests.datasets`, `manifests.models`, `telemetry.events`

**Exit Criteria (updated):**

| Criterion | Status |
|---|---|
| End-to-end ingest (local pipeline) | **Done** |
| Immutable raw + curated with checksum/provenance | **Done** |
| PII / toxicity / relevance / dedup gates | **Done** |
| Demo vs real isolation + run_id folders | **Done** |
| EN/HI/MR discovery + trusted allow-list | **Done** |
| Partial corpus + failure report for mixed runs | **Done** |
| Cleanup/reset API + scripts | **Done** |
| Temporal durable path default in prod | **Partial** (supported; local fallback common) |
| Iceberg/Parquet lake (vs JSONL local) | **Planned** (JSONL local lakehouse today) |

#### Phase 3 — Knowledge Graph and GraphRAG Plane

**Objective:** Convert curated data into a factual agricultural knowledge graph.

**Knowledge Graph Nodes:**
```
Crop, Disease, Pest, Chemical, Fertilizer, Symptom, 
Treatment, Dosage, SoilType, WeatherCondition, Season, 
GovernmentScheme, Market, Location, Variety, Practice
```

**Knowledge Graph Edges:**
```
(Crop)-[:AFFECTED_BY]->(Disease)
(Disease)-[:HAS_SYMPTOM]->(Symptom)
(Disease)-[:TREATED_BY]->(Chemical)
(Chemical)-[:HAS_DOSAGE]->(Dosage)
(Crop)-[:GROWS_IN]->(SoilType)
(Crop)-[:REQUIRES]->(Practice)
... with source_id, confidence, valid_from, valid_to
```

**GraphRAG Strategy:**
- Local GraphRAG for precise multi-hop: `Crop -> Disease -> Treatment -> Dosage` with exact traversal
- Global GraphRAG for broad advisory: community summaries + vector search
- Vector RAG for semantic similarity and fuzzy recall
- API RAG for live weather, market, soil data

**Graph Quality Rules:** No orphan facts, no unsafe dosage without approved source, human approval for high-risk entities, ontology aliases for Marathi/Hindi/English, temporal validity.

**Exit Criteria:** Ontology schema defined, entity extraction pipeline writes to staging graph, production graph only accepts approved entities, GraphRAG returns citations, unsafe dosage answers blocked.

#### Phase 4 — Model Factory

**Objective:** Build the model pipeline from tokenizer to deployment.

**Model Family Strategy:**

| Model | Role |
|---|---|
| 18M edge model | Offline rural inference, fast, low memory |
| 7B/14B cloud model | Complex reasoning, tool planning, graph synthesis |
| Large teacher model | Synthetic data generation and evaluation |
| Vision model | Crop disease image analysis (EfficientNet/ConvNeXt fine-tune) |
| Embedding model | Retrieval and semantic cache (BGE-Multilingual) |

**Tokenizer Control:**
```json
{
  "tokenizer_id": "agrimind-tokenizer-v1",
  "vocab_size": 64000,
  "model_family": "agrimind-18m",
  "checksum": "sha256:...",
  "languages": ["en","hi","mr"],
  "normalization": "NFKC + Marathi/Hindi transliteration map"
}
```

**Model Manifest:**
```json
{
  "model_id": "agrimind-7b-v1.0.3",
  "base_model": "Qwen2.5-7B",
  "tokenizer_manifest_id": "agrimind-tokenizer-v1",
  "dataset_manifest_id": "ds-2026-05-01-v4",
  "training_config": "lora_r16_alpha32",
  "eval_score": {"faithfulness": 0.93, "safety": 1.0},
  "artifact_path": "s3://agrimind-models/7b/v1.0.3"
}
```

**Training Pipeline:**
```
Dataset Manifest Validation
-> Tokenizer Match Check (fail loud)
-> Dataset Preparation (instruction + DPO pairs)
-> LoRA/QLoRA Fine-tune (FSDP)
-> Eval Harness (golden set)
-> ONNX Export (for edge)
-> Model Manifest Generation
-> Registry Upload
```

**Exit Criteria:** Model manifest immutable, tokenizer manifest immutable, eval harness blocks bad models, edge model can export to ONNX, cloud model can serve through inference service.

#### Phase 5 — Retrieval and Memory Service

**Objective:** Build the memory engine that feeds the agents.

**Retrieval Modes:**

| Mode | Use Case |
|---|---|
| Graph exact retrieval | Precise crop/disease/chemical queries |
| Vector semantic retrieval | Broad advisory queries |
| Hybrid retrieval | Combined graph + vector with reranking |
| API retrieval | Live weather, market, satellite |
| Semantic cache | Frequently repeated farmer questions |

**Retrieval Contract:**
```python
class RetrievalRequest(BaseModel):
    query: str
    lang: str
    mode: Literal["graph","vector","hybrid","api","auto"]
    top_k: int = 8
    filters: dict

class RetrievalResult(BaseModel):
    chunks: list[ChunkWithCitation]
    graph_paths: list[GraphPath]
    confidence: float
    trace: RetrievalTrace
```

**Semantic Cache:** Use embeddings to cache repeated questions like "Kapusavaril thrips sathi upay?" -> canonical intent.

**Exit Criteria:** Hybrid retrieval working, graph and vector results include citations, semantic cache invalidates on knowledge update, retrieval p95 < 300ms.

#### Phase 6 — Agent Orchestrator and Safety Engine

**Objective:** Build the intelligent brain that plans, retrieves, uses tools, and checks itself.

**Agent Graph (LangGraph):**
```
START -> intent_classifier -> language_router
-> retrieval_planner [decides graph/vector/api]
-> retriever -> reranker
-> tool_planner [weather/market/vision]
-> generator (LLM)
-> safety_checker -> confidence_gate
-> IF confidence < threshold -> fallback_or_human
-> ELSE -> response_formatter (with citations)
-> END
```

**Agent State:**
```python
class AgentState(TypedDict):
    query: Query
    intent: str
    retrieval_results: RetrievalResult
    tool_outputs: dict
    draft_answer: str
    safety_flags: list
    confidence: float
    citations: list[Citation]
```

**Epistemic Guardrail:**

| Category | Minimum Confidence |
|---|---|
| General advisory | 0.70 |
| Pest treatment | 0.85 |
| Chemical dosage | 0.95 or human fallback |
| Legal/scheme advice | 0.90 |
| Weather-sensitive action | 0.85 |

**Safety Policy Engine Blocks:** Unsafe pesticide dosage, banned chemicals, harmful mixing advice, human health claims, veterinary claims without disclaimer, legal/financial guarantees, PII leakage, prompt injection.

**Exit Criteria:** Agent graph bounded and observable, tool calls have timeouts/retries, safety engine blocks high-risk hallucinations, low-confidence queries fallback safely.

#### Phase 7 — Inference Service and Edge-Cloud Continuum

**Objective:** Serve models reliably in cloud and edge.

**Cloud Inference (SGLang/vLLM):** Continuous batching, streaming, structured output, token budgets, request cancellation, GPU telemetry.

**Edge Inference (ONNX Runtime / MLC-LLM):** Quantized INT4/INT8, small memory footprint (< 500MB), offline mode, local cache, sync queue for delayed connectivity.

**Inference Router:**
```
IF offline -> Edge 18M + local cache
ELIF FAQ cache hit -> Semantic cache
ELIF complex multi-hop -> Cloud 14B + GraphRAG
ELIF chemical dosage -> Graph exact + human fallback
ELSE -> Cloud 7B + Hybrid RAG
```

**Exit Criteria:** Cloud inference stable, edge inference exportable, router chooses correct model, model version visible in response metadata.

#### Phase 8 — Autonomous Self-Learning Flywheel

**Objective:** Make the platform self-improving with quality gates. This is the autonomous moat.

**Flywheel Stages:**
```
1. Signal Collection (feedback, low confidence, retrieval miss)
2. Failure Clustering
3. Root Cause Classification
4. Gap Repair Planning
5. Research Agent (approved sources)
6. Candidate Data Generation (teacher model)
7. Quality Filtering
8. Staging Index/Graph Update
9. Evaluation (golden set + safety)
10. Human Approval Gate (if high-risk)
11. Canary Promotion
12. Auto-Rollback on regression
13. Audit Log
```

**Signals to Collect:** User thumbs up/down, repeat question, session abandonment, low confidence, retrieval miss, tool failure, safety flag, expert correction, language mismatch, high latency.

**Failure Root Cause Taxonomy:**

| Root Cause | Fix |
|---|---|
| Retrieval gap | Improve embedding, chunking, alias |
| Knowledge graph gap | Graph repair workflow |
| Prompt gap | Prompt patch and eval |
| Tool gap | Add fallback or mapping |
| Language gap | Add dialect data and eval |
| Model gap | DPO/fine-tune with corrective data |
| Safety gap | Add safety rule and eval |
| Data quality gap | Quarantine source and reindex |

**Nightly Self-Review Jobs:** confidence histogram, hallucination scan, retrieval miss report, safety violation review, language quality drift, cost analysis.

**Exit Criteria:** Feedback loop captured end-to-end, failure taxonomy automated, synthetic data quality-filtered, canary rollback works.

#### Phase 9 — Expert Console and Human-in-the-Loop

**Objective:** Allow agronomists, language experts, and administrators to review the system.

**Expert Console Features:** Review low-confidence answers, correct answers, approve KG changes, approve synthetic datasets, review safety incidents, manage source allow-lists, manage model promotion, review eval reports, manage kill switches, audit all changes.

**Approval Levels:**

| Change Type | Approval Required |
|---|---|
| Prompt patch | AI lead or product owner |
| Retrieval index update | Automated if eval passes |
| Graph non-risk node | Automated or reviewer |
| Graph chemical/dosage node | Agronomist approval |
| Model promotion | AI lead + safety owner |
| Source allow-list change | Compliance owner |
| Emergency stop | Admin/security owner |

#### Phase 10 — Production Hardening

**Security Requirements:** OIDC/API key, tenant + RBAC, Vault/KMS secrets, TLS + encryption at rest, PII redaction, immutable audit logs, SBOM/CVE scanning, Trivy container scan, prompt injection defense, rate limiting per user/tenant/IP.

**Reliability Requirements:** Health checks (liveness/readiness), idempotent retries with backoff, circuit breakers, timeouts, dead-letter queues, backups (Postgres, MinIO, Neo4j, Qdrant), disaster recovery drills, graceful degradation.

**Observability Requirements:** Structured JSON logs with request ID, end-to-end traces, latency/error/saturation metrics, AI metrics (confidence, hallucination flags, retrieval hits), cost metrics, dashboards, alerts.

---

### 12. Quality Filter Matrix

**Data Filters:**

| Filter | Stage | Blocking? |
|---|---|---|
| Source allow-list | Ingestion | Yes |
| License validation | Ingestion | Yes |
| robots.txt policy | Ingestion | Yes |
| Payload size limit | Download | Yes |
| Checksum integrity | Storage | Yes |
| Language detection | Curation | Yes |
| PII redaction | Curation | Yes |
| Safety/toxicity | Curation | Yes |
| Agriculture relevance | Curation | Yes |
| Deduplication | Curation | Yes |
| Quality score | Curation | Yes |
| Expert approval | High-risk data | Conditional |

**Retrieval Filters:** Source freshness (Conditional), Source license (Yes), Citation availability (Yes), Relevance score (Yes), Safety policy (Yes)

**Model Filters:** Tokenizer match (Yes), Dataset manifest match (Yes), Eval threshold (Yes), Safety threshold (Yes), Language threshold (Yes), Latency threshold (Yes), Edge resource threshold (Yes)

---

### 13. Accuracy Improvement Plan

#### 13.1 Accuracy Definition

| Accuracy Type | Meaning |
|---|---|
| Retrieval accuracy | Did we retrieve the right evidence? |
| Graph accuracy | Are facts and relations correct? |
| Generation accuracy | Did the model use evidence correctly? |
| Tool accuracy | Did tools return correct external data? |
| Language accuracy | Is the answer natural in Marathi/Hindi/English? |
| Safety accuracy | Did we avoid unsafe or forbidden advice? |
| Actionability accuracy | Can the farmer act on the answer safely? |

#### 13.2 Low Accuracy Response Flow

```
1. Detect low accuracy (eval, feedback, confidence)
2. Classify root cause (taxonomy)
3. Create repair ticket
4. Research agent fetches evidence (approved sources)
5. Generate candidate fix (graph node / chunk / training data)
6. Quality filter
7. Stage update
8. Run golden eval + safety eval
9. IF high-risk -> Expert approval
10. ELSE IF eval passes -> Canary
11. Monitor canary
12. Promote or rollback
13. Audit log + close loop
```

#### 13.3 Accuracy Thresholds

| Metric | Development Target | Production Target |
|---|---|---|
| Faithfulness | >= 0.90 | >= 0.95 |
| Answer relevance | >= 0.85 | >= 0.90 |
| Context precision | >= 0.85 | >= 0.92 |
| Tool success rate | >= 95% | >= 99% |
| PII leakage | 0 | 0 |
| Safety violation | 0 | 0 |
| Hallucination rate | < 3% | < 1% |
| Language quality | >= 0.85 | >= 0.90 |
| p95 latency cloud | < 3s | < 2s |
| Edge inference time | < 4s | < 2.5s |

---

### 14. Data Loss Prevention Plan

**Data Loss Risks & Controls:**

| Risk | Example | Control |
|---|---|---|
| Connector failure | Source website down | Retry, backoff, backfill |
| Schema drift | Source JSON changes | Contract validation |
| Object corruption | MinIO/S3 corruption | Checksum and versioning |
| Workflow failure | Temporal worker crash | Durable execution and resume |
| Duplicate processing | Same doc processed twice | Idempotency keys |
| Missing lineage | Unknown training data origin | Manifests |
| Deleted raw data | Curated data cannot be rebuilt | Immutable raw storage |
| Index loss | Vector/graph index corrupted | Rebuild from lakehouse |

**Mandatory Controls:**
- Every ingested object gets SHA-256 checksum
- Every dataset version gets manifest ID
- Every model references dataset manifest ID
- Raw data is immutable
- Curated data is rebuildable from raw data
- Vector and graph indexes are rebuildable
- Failed workflows go to dead-letter queue
- Backup jobs run automatically
- Restore drills performed monthly

---

### 15. Test-Driven Development Strategy

#### 15.1 Test Pyramid

```
Unit Tests (70%) -> Fast, isolated
Contract Tests (15%) -> Schema validation
Integration Tests (10%) -> DBs, Queues, Temporal
E2E & Golden Eval (5%) -> Full agent flow + safety
```

#### 15.2 Required Test Suites

| Suite | Purpose |
|---|---|
| Unit tests | Business logic, validators, utilities |
| Contract tests | API schemas and inter-service contracts |
| Integration tests | Postgres, Neo4j, Qdrant, Temporal, Redis |
| Retrieval tests | Golden retrieval queries |
| Graph tests | Ontology traversal and safety constraints |
| Agent tests | Tool use, routing, fallback |
| Safety tests | Harmful prompt resistance |
| Language tests | Marathi/Hindi/English fluency |
| Model eval tests | Golden answer quality |
| Load tests | Latency and throughput |
| Chaos tests | Failure recovery |
| Security tests | Auth, injection, rate limit |

#### 15.3 Golden Dataset Structure

```json
{
  "id": "q_en_crop_disease_001",
  "lang": "mr",
  "query": "कपाशीवर बोंडअळी आली आहे, काय करावे?",
  "expected_intent": "pest_treatment",
  "expected_entities": ["cotton", "bollworm"],
  "expected_graph_path": ["Cotton -AFFECTED_BY-> Bollworm -TREATED_BY-> ..."],
  "must_cite": true,
  "safety_level": "high",
  "expected_answer_contains": ["IPM", "safety"],
  "forbidden_tokens": ["100ml per liter"]
}
```

---

### 16. CI/CD Pipeline Design

#### 16.1 Pull Request Pipeline

```
1. lint (ruff)
2. type-check (mypy)
3. unit tests
4. contract tests
5. import-layer check (import-linter)
6. security scan (bandit + pip-audit)
7. build docker images
8. integration tests (docker-compose)
9. retrieval golden tests
10. safety eval (adversarial prompts)
11. container scan (trivy)
12. fail if any blocking gate fails
```

#### 16.2 Model Promotion Pipeline

```
1. Validate model manifest + tokenizer manifest
2. Checkpoint load test
3. Golden eval (faithfulness, relevance, context precision)
4. Safety eval (zero tolerance for dosage hallucination)
5. Language eval (hi/mr/en fluency)
6. Latency eval (p95, TTFT)
7. Edge export test (ONNX)
8. Canary deployment (5% traffic)
9. Monitor 24h (error rate, confidence, feedback)
10. Auto-promote to production OR auto-rollback
```

#### 16.3 Required CI Gates

| Gate | Blocking |
|---|---|
| Lint | Yes |
| Type check | Yes |
| Unit tests | Yes |
| Contract tests | Yes |
| Import layer rules | Yes |
| Security scan | Yes |
| Safety eval | Yes |
| Golden eval regression | Yes |
| Container scan | Yes |
| Performance smoke | Conditional |

---

### 17. Deployment Environments

| Environment | Purpose |
|---|---|
| local | Developer machine with Docker Compose |
| dev | Shared development cluster |
| staging | Production-like environment with eval gates |
| canary | Small production traffic (5%) |
| production | Full production traffic |
| offline-edge | Device-local deployment |

**Promotion Rules:**
```
local -> dev (CI passes)
dev -> staging (integration + retrieval tests pass)
staging -> canary (golden + safety eval pass + human approval for model)
canary -> production (24h SLO met, no regression)
production -> offline-edge (edge export + resource check)
```

---

### 18. Observability and Self-Review Dashboards

#### 18.1 Product Dashboards

| Dashboard | Metrics |
|---|---|
| Farmer experience | sessions, repeat questions, thumbs down, abandonment |
| Answer quality | confidence, citations, fallback rate |
| Language usage | en/hi/mr distribution and quality |
| Safety | safety flags, blocked answers, high-risk queries |

#### 18.2 AI Dashboards

| Dashboard | Metrics |
|---|---|
| Retrieval | hit rate, context precision, latency |
| Graph | missing entity rate, traversal failures |
| Model | token usage, confidence, hallucination flags |
| Tools | API success rate, timeout rate |
| Flywheel | correction volume, retraining candidates |

#### 18.3 Infrastructure Dashboards

| Dashboard | Metrics |
|---|---|
| API | p50/p95/p99 latency, error rate |
| Inference | GPU/CPU, queue depth, TTFT |
| Data pipeline | job success, quarantine volume |
| Storage | object growth, backup status |
| Cost | tokens, compute, storage, third-party APIs |

---

### 19. Security, Privacy, and Compliance

#### 19.1 Legal and Data Governance

| Control | Requirement |
|---|---|
| Source approval | Only approved sources may be ingested |
| License tracking | Every document stores license metadata |
| robots.txt | Must be respected |
| PII handling | Redaction and retention controls |
| Deletion requests | Must propagate to lakehouse and indexes |
| Audit trail | Must be immutable |
| Consent | Owner-authorized media only |

#### 19.2 AI Safety

| Control | Requirement |
|---|---|
| High-risk advice | Chemical dosage requires citation or fallback |
| Prompt injection | Inputs sanitized and tools constrained |
| Jailbreak resistance | Safety eval includes adversarial prompts |
| Output filtering | Responses checked before delivery |
| Kill switch | Dangerous feature can be disabled instantly |

---

### 20. Milestone Plan

| Milestone | Deliverable |
|---|---|
| **M0 — Foundation Ready** | Monorepo, Docker Compose, Kernel contracts, CI gates, golden folder |
| **M1 — Data Lake Ready** | **As-built:** local IngestPipeline, run-scoped lakehouse, demo/real modes, EN/HI/MR discovery, PII/toxicity/relevance/dedup, provenance, quarantine, failure reports, cleanup. Temporal optional. Iceberg promotion remaining. |
| **M2 — Knowledge Memory Ready** | Ontology, GraphRAG, Hybrid retrieval, citation enforcement |
| **M3 — Agent Brain Ready** | LangGraph orchestrator, tools, safety engine, confidence gates, tracing |
| **M4 — Model Factory Ready** | Tokenizer manifests, model manifests, LoRA/DPO pipeline, eval harness, ONNX export |
| **M5 — Edge-Cloud Ready** | Cloud inference (vLLM/SGLang), edge inference, router, semantic cache |
| **M6 — Flywheel Ready** | Feedback ingestion, root cause classifier, repair workflows, canary rollback |
| **M7 — Production Flagship Ready** | Security scan pass, backup/restore drill, load/chaos tests, dashboards live, runbooks |

---

### 21. Team Roles

| Role | Responsibility |
|---|---|
| Principal AI Architect | Overall architecture, layer enforcement, AI safety |
| AI Platform Engineer | Model factory, inference, registry, training |
| Data Platform Engineer | Temporal pipelines, lakehouse, curation |
| Knowledge Engineer | Ontology, GraphRAG, entity extraction |
| Agent Engineer | LangGraph workflows, tools, routing |
| Backend Engineer | FastAPI services, gateway, contracts |
| MLOps Engineer | CI/CD, Kubernetes, observability, canary |
| Evaluation Engineer | Golden datasets, eval harness, judge calibration |
| Agronomy Domain Expert | Validate crop/disease/chemical knowledge |
| Language Expert | Marathi/Hindi fluency, dialects, voice UX |
| Security Engineer | PII, auth, prompt injection, compliance |

---

### 22. Definition of Flagship Production Ready

**Engineering:**
- Monorepo builds reproducibly
- CI passes all gates
- Import layer rules enforced
- All services have health checks
- All external calls have timeouts and retries
- All secrets managed via Vault/KMS
- All containers scanned
- Backups and restore drills pass

**Data:**
- Data lake has provenance
- PII redaction passes tests
- Deduplication measured
- Dataset manifests immutable
- Quarantine workflow operational
- **Demo and real corpora isolated by `acq_mode` + `run_id`**
- **Partial run success exposes curated corpus + failure report**
- **Cleanup/reset can free disk without wiping the wrong mode**

**AI Quality:**
- Golden eval passes
- Safety eval passes
- Language eval passes for en/hi/mr
- Retrieval quality measured
- Graph provenance enforced
- Hallucination rate below threshold (<1%)

**Autonomy:**
- Feedback captured
- Failures classified
- Repair workflows propose fixes
- Synthetic data passes filters
- Model promotion eval-gated
- Canary rollback works automatically

**Product:**
- Farmer can receive useful advice
- Unsafe advice blocked
- Answers include citations where required
- Offline mode works
- Expert console can correct answers
- Audit trail complete

---

### 23. Principal Architect Decision Log

| Decision | Rationale |
|---|---|
| Use monorepo with strict packages | Prevents fragmentation and import cycles |
| Use Temporal for data pipeline | Durable execution mandatory for autonomous curation |
| Use GraphRAG + Vector RAG | Agriculture requires exact facts and semantic recall |
| Use ontology with citations | Reduces hallucination and improves explainability |
| Use immutable manifests | Makes data/model/training reproducible |
| Use eval-gated deployment | Prevents silent regressions |
| Use human approval for high-risk graph changes | Chemical/dosage advice must be safe |
| Use edge-cloud routing | Rural connectivity requires offline intelligence |
| Use self-learning flywheel with gates | Autonomy must be safe and auditable |
| **Demo vs real DAQ isolation** | Mock data must never contaminate real agri corpus |
| **run_id-scoped lakehouse folders** | Process auditability + partial success corpus per run |
| **EN/HI/MR keyword discovery** | Local-language first acquisition, not EN-only crawl |
| **Object store auto→local fallback** | Local dev without MinIO must not spam connection errors |
| **Failure reports for partial runs** | Track download/size/HTTP classes without discarding successes |
| **Kustomize base + overlays** | local/prod/gpu separation without forking full manifests |
| **Compose for data plane, K8s for scale** | Laptop vs cluster paths both first-class |

---

### 24. Immediate Next Actions

#### 24.1 Completed foundation (do not re-scaffold)

1. ~~Monorepo with uv workspace~~ (exists under `agrimind/`)
2. ~~Docker Compose core services~~ (`docker-compose.yml`)
3. ~~Kernel contracts + safety engine~~ (`packages/agrimind-kernel`)
4. ~~Phase 2 local data acquisition plane~~ (see §26)
5. ~~DAQ UI + Windows env launchers~~

#### 24.2 Near-term (recommended order)

1. Keep **REAL** DAQ runs healthy: refresh seed catalog URLs that 404; prefer `source_cache` for large PDFs
2. Persist job registry beyond process memory (Postgres) so restart retains Live Jobs
3. Promote JSONL lakehouse tables toward Iceberg/Parquet for scale analytics
4. Wire Temporal as default for multi-day crawls; keep local pipeline for laptop demos
5. Expand golden eval (en/hi/mr) and retrieval golden set against curated chunks
6. GraphRAG over curated corpus from successful real runs
7. LangGraph agent + safety fallback consuming GraphRAG
8. Observability: OTEL traces for ingest stages + `run_id` attributes; compose stack for Grafana
9. **Infra:** add `data-ingestion-service` to k8s base + PVC for `data/runs`
10. **Infra:** optional `docker-compose.observability.yml` using `infra/observability/*`

#### 24.3 Quick DAQ operator commands

```bat
REM From repo root AGRIMIND\
start-daq-all.bat local
REM API  http://127.0.0.1:8017/docs
REM UI   http://127.0.0.1:5173

cleanup-daq-data.bat preview real
cleanup-daq-data.bat delete real
```

```powershell
cd agrimind
uv run python scripts/discover_agri_sources.py -k "cotton,soil health" --langs en,hi,mr
```

---

### 25. Final Flagship Statement

> AGRIMIND must be built as a self-improving agricultural intelligence system, not a simple LLM wrapper.

The moat comes from the combination of:

1. **Proprietary curated agricultural data** with full provenance
2. **Multilingual Marathi/Hindi/English capability** as first-class
3. **Graph-grounded factual reasoning** to prevent hallucinations
4. **Edge-first rural deployment** for real Bharat
5. **Autonomous quality flywheel** with safe gates
6. **Expert-reviewed agronomy knowledge**
7. **Production-grade safety and observability**

**Farmer safety first. Explainability always. Offline always works.**

---

### 26. As-Built Data Acquisition Plane (Implementation Snapshot)

> This section documents **what is implemented in the monorepo today**, not only aspirational design. Prefer these paths when operating or extending DAQ.

#### 26.1 Architecture (as-built)

```mermaid
flowchart LR
  UI[DAQ Frontend :5173] -->|/api proxy| API[data-ingestion-service :8017]
  API --> Discover[Keyword + Online Discovery EN/HI/MR]
  API --> Runs[Run Registry acq_mode + run_id]
  API --> Pipe[IngestPipeline stages 1-13]
  Discover --> Allow[Trusted allow-list + trust score]
  Pipe --> Demo[data/runs/demo-*]
  Pipe --> Real[data/runs/real-*]
  Demo --> Tables[(JSONL tables + objects)]
  Real --> Tables
  API --> Report[Failure / partial report]
  API --> Clean[POST /v1/admin/cleanup]
```

#### 26.2 Modes and isolation

| Concern | DEMO | REAL |
|---|---|---|
| Purpose | Offline QA walkthrough | Production-like agri corpus |
| Sources | `example.com` + inline content | Wikipedia / FAO / ICAR / USDA / Archive (allow-listed) |
| API | `POST /v1/qa/demo-batch` | `POST /v1/ingest/batch` `acq_mode=real` |
| Storage | `data/runs/demo-{ts}-{id}/` | `data/runs/real-{ts}-{id}/` |
| Mixing | **Never** write into real lakehouse | Rejects demo URLs and inline mock content |

#### 26.3 Package map

| Package / service | Responsibility |
|---|---|
| `data_kernel.sources.discovery` | Allow-list (~70+ hosts), license/trust/provider inference, seed catalog en/hi/mr, access check |
| `data_kernel.sources.keyword_discovery_service` | EN/HI/MR keyword expand, Wikipedia/Archive/OL/FAO search, PDF books, optional FastAPI factory |
| `data_kernel.sources.online_discovery` | Category taxonomy discovery + access probes |
| `data_kernel.sources.connectors` | Fetch web/pdf/wiki/rss; Archive metadata PDF resolve; large PDF partial extract |
| `data_kernel.pipeline.ingest_pipeline` | Full stage pipeline + live progress callbacks |
| `data_ingestion_service.runs` | `run_id` folders, process log, cleanup |
| `data_ingestion_service.main` | REST API: ingest, batch, runs, corpus, report, cleanup |
| `data_ingestion_service.qa` | Dashboard, enrich job, failure classification, run reports |
| `frontend/data-acquisition` | Operator UI: REAL/DEMO, discover, live jobs, partial corpus, failure report download |

#### 26.4 Operator runbook

1. Start stack: `start-daq-all.bat local`
2. Open UI → select **REAL mode** → **Real sources** (or Discover EN/HI/MR → ingest ready)
3. Monitor **Live Jobs** for stage %; failures show class (`size_limit`, `timeout`, `http_not_found`, …)
4. Open **Ready Corpus** with active `run_id` for **partial** curated documents/chunks
5. Generate **failure report**: `GET /v1/runs/{run_id}/report` (also saved under `runs/.../reports/`)
6. Free disk: `cleanup-daq-data.bat preview real` then `delete real` if intentional

#### 26.5 Known limitations / next upgrades

| Item | Notes |
|---|---|
| In-memory job registry | Restart clears Live Jobs memory; disk snapshots under `runs/*/jobs/` remain |
| JSONL not Iceberg | Local lakehouse is JSONL + object files; analytics scale later |
| Temporal | Registered workflows exist; laptop path uses local pipeline |
| External source fragility | Some gov/Archive URLs 403/404/503 — discovery + failure report track this |
| Object store | `OBJECT_STORE=local` default; MinIO optional via `auto` |

#### 26.6 Related documents

- `agrimind/docs/data-discovery-improvement-plan/SOURCE_DISCOVERY_GUIDE.md`
- `agrimind/docs/data-discovery-improvement-plan/IMPLEMENTATION_STATUS.md`
- `agrimind/MERGE_AND_IMPROVEMENT_PLAN.md`
- `env/README.md` (DAQ env bat files)

---

### 27. As-Built Infrastructure & Deployment Map

> **Why this section exists:** Infra was present in the repo (`agrimind/infra/`, compose files) but under-documented when §26 focused on DAQ. This is the full **deploy / observe / GPU** map with use-comments.

#### 27.1 Infra folder structure (use comments)

```text
agrimind/infra/
├── k8s/                                # use: Kubernetes deploy via Kustomize
│   ├── base/                           # use: shared Deployments + Service + ConfigMap
│   │   ├── namespace.yaml              # use: agrimind namespace
│   │   ├── configmap.yaml              # use: non-secret env for services
│   │   ├── services.yaml               # use: ClusterIP service definitions
│   │   ├── gateway-deployment.yaml     # use: edge gateway pods
│   │   ├── assistant-api-deployment.yaml
│   │   ├── agent-orchestrator-deployment.yaml
│   │   ├── memory-service-deployment.yaml
│   │   ├── inference-service-deployment.yaml
│   │   └── kustomization.yaml          # use: lists base resources + common labels
│   └── overlays/
│       ├── local/                      # use: low CPU/RAM patches for dev clusters
│       │   ├── kustomization.yaml
│       │   └── local-resources-patch.yaml
│       ├── prod/                       # use: production kustomization (replicas/limits)
│       │   └── kustomization.yaml
│       └── gpu/                        # use: add GPU vLLM workload
│           └── vllm-deployment.yaml
│
├── observability/                      # use: metrics, logs, traces, Grafana
│   ├── prometheus.yml                  # use: scrape service metrics endpoints
│   ├── otel-collector-config.yaml      # use: receive OTLP; export to Prometheus/Loki/…
│   ├── loki-config.yaml                # use: log store config
│   ├── datasources/datasources.yml     # use: Grafana auto-provision Prometheus/Loki
│   ├── dashboards/                     # use: JSON dashboards loaded by Grafana
│   │   ├── agrimind-system-overview.json  # use: CPU/mem/latency SLO view
│   │   ├── agrimind-ai-quality.json       # use: retrieval/model quality panels
│   │   ├── system-health.json
│   │   ├── ai-quality.json
│   │   └── dashboards.yml              # use: dashboard provider config
│   └── alerts/agrimind-alerts.yml      # use: PrometheusRule-style alert definitions
│
└── vllm/
    └── README.md                       # use: how to run GPU vLLM + wire inference-service
```

**Compose (sibling to `infra/`, under `agrimind/`):**

| File | Use |
|---|---|
| `docker-compose.yml` | Local data plane: Postgres, MinIO, Neo4j, Qdrant, Redis, Temporal |
| `docker-compose.vllm.yml` | Optional GPU inference server (OpenAI-compatible) |

#### 27.2 Deploy environments flow

```mermaid
flowchart LR
  Dev[Developer laptop] -->|docker compose up| LocalInfra[Compose: PG MinIO Neo4j Qdrant Redis Temporal]
  Dev -->|start-daq-*.bat| DAQ[DAQ API + UI]
  LocalInfra --> DevCluster[k8s overlay: local]
  DevCluster -->|CI pass| Staging[k8s overlay: prod-like]
  Staging -->|golden+safety eval| Canary[canary traffic]
  Canary -->|SLO 24h| Prod[k8s overlay: prod]
  Prod -->|optional| GPU[k8s overlay: gpu + vLLM]
  GPU --> Inf[inference-service remote backend]
```

#### 27.3 Request / observability flow

```mermaid
flowchart TB
  Client[Farmer / Operator client] --> GW[gateway-service]
  GW --> Svc[assistant / orchestrator / memory / inference / DAQ]
  Svc -->|OTLP| OTEL[otel-collector]
  OTEL --> Prom[Prometheus]
  OTEL --> Loki[Loki]
  Prom --> Graf[Grafana dashboards]
  Loki --> Graf
  Prom --> Alerts[agrimind-alerts.yml]
```

#### 27.4 What is deployed where (as-built vs planned)

| Component | Local compose | K8s base | Notes |
|---|---|---|---|
| Postgres | **Yes** | Planned/secret map | Feedback DSN, future job registry |
| MinIO | **Yes** | Planned | DAQ often uses `OBJECT_STORE=local` on laptop |
| Neo4j | **Yes** | Planned | GraphRAG |
| Qdrant | **Yes** | Planned | Vector retrieval |
| Redis | **Yes** | Planned | Semantic cache |
| Temporal | **Yes** | Planned | Curation worker |
| gateway / assistant / orchestrator / memory / inference | Dockerfiles exist; k8s base **Yes** | **Yes** | Scale path |
| **data-ingestion-service** | **uv/bat local** | Not yet in k8s base | Add Deployment when DAQ goes cluster |
| vLLM GPU | `docker-compose.vllm.yml` | `overlays/gpu` | Optional; needs NVIDIA |
| Grafana/Prometheus/Loki | configs in `infra/observability` | wire via compose/k8s | Config present; full stack wiring ongoing |

#### 27.5 Operator commands (infra)

```bash
# Local data plane
cd agrimind
docker compose up -d
docker compose ps

# Optional GPU inference
docker compose -f docker-compose.vllm.yml up -d
# see infra/vllm/README.md for VLLM_MODEL / smoke scripts

# Kubernetes (from agrimind/)
kubectl apply -k infra/k8s/overlays/local
# kubectl apply -k infra/k8s/overlays/prod
# kubectl apply -k infra/k8s/overlays/gpu
```

```bat
REM DAQ app (does not replace compose; uses local FS store by default)
start-daq-all.bat local
```

#### 27.6 Infra gaps (honest backlog)

| Gap | Impact | Suggested next step |
|---|---|---|
| DAQ service missing from k8s base | Cluster cannot run discovery/ingest yet | Add `data-ingestion-deployment.yaml` + PVC for `data/runs` |
| Observability configs not fully wired into compose | Dashboards may need manual Grafana import | Add `docker-compose.observability.yml` (Prometheus+Grafana+Loki+OTEL) |
| No dedicated `infra/temporal/` manifests | Temporal only via compose image | K8s Temporal Helm or operator later |
| Secrets still env-based | Not Vault/KMS | ExternalSecrets / SealedSecrets in prod overlay |
| data-ingestion not in CI deploy matrix | Only unit-tested locally | Add service image + smoke job |

#### 27.7 Mental model: three “planes”

| Plane | Folders | Use when |
|---|---|---|
| **App plane** | `packages/`, `services/`, `workers/`, `frontend/` | Writing product code |
| **Data plane** | `data/runs`, `data/source_cache`, lakehouse tables | Ingest, QA, cleanup |
| **Infra plane** | `infra/`, `docker-compose*.yml`, `.github/` | Deploy, scale, observe, GPU |

Do not put application business logic under `infra/`. Do not put cluster YAML under `packages/`.

---

*Generated: AGRIMIND Implementation Plan — living document*  
*Last infra/repo map update: 2026-08-08*  
*Owner: Principal AI Systems Architect*
