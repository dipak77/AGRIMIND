# AGRIMIND — From-Scratch Implementation Plan
## Autonomous Agricultural Intelligence Engine

**Document Type:** Principal AI Systems Architecture & Implementation Plan  
**Architecture Level:** Flagship / Production / 2026 Cutting-Edge AI Platform  
**Target Domain:** Agri-Tech AI  
**Languages:** English, Hindi, Marathi  
**Primary Goal:** Build an autonomous, self-learning, self-improving, production-grade agricultural intelligence platform with a defensible AI moat.

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

- Autonomous data ingestion from approved sources
- PDF, web, RSS, Wikipedia, JSON, image, audio, and structured dataset processing
- PII redaction
- License and source governance
- Duplicate detection
- Language filtering
- Agriculture relevance scoring
- Knowledge graph construction
- Vector retrieval construction
- Synthetic training data generation
- Model evaluation, fine-tuning, canary deployment, automatic rollback
- Expert review console

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

### 8. From-Scratch Repository Layout

```text
agrimind/
├── pyproject.toml              # uv workspace root
├── Makefile
├── docker-compose.yml
├── .env.example
├── README.md
├── ADRs/
│   └── 001-monorepo-layering.md
├── packages/
│   ├── kernel/
│   │   ├── contracts/          # Query, Response, Citation, Safety
│   │   ├── config/
│   │   ├── errors/
│   │   └── telemetry/
│   ├── data-kernel/
│   │   ├── manifests/
│   │   └── lakehouse/
│   ├── memory/
│   │   ├── graph/
│   │   ├── vector/
│   │   └── retrieval/
│   ├── models/
│   │   ├── tokenizer/
│   │   ├── inference/
│   │   └── registry/
│   ├── agents/
│   │   ├── graphs/
│   │   ├── tools/
│   │   └── safety/
│   └── eval/
│       ├── golden/
│       │   ├── en/
│       │   ├── hi/
│       │   └── mr/
│       └── harness/
├── services/
│   ├── gateway-service/
│   ├── assistant-api/
│   ├── agent-orchestrator/
│   ├── memory-service/
│   ├── inference-service/
│   ├── vision-service/
│   ├── feeds-service/
│   ├── data-ingestion-service/
│   ├── eval-service/
│   ├── expert-console-api/
│   └── admin-service/
├── workers/
│   ├── curation-worker/
│   └── training-orchestrator/
├── infra/
│   ├── temporal/
│   └── k8s/
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    ├── retrieval/
    ├── safety/
    └── load/
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
POSTGRES_DSN=postgresql+asyncpg://agrimind:agrimind@localhost:5432/agrimind
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
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

**Objective:** Build the pre-stage autonomous data lake.

**Data Sources:**

| Source Type | Example |
|---|---|
| Web | approved agricultural websites (ICAR, agri dept) |
| PDF | agronomy manuals, scheme documents |
| Wikipedia | agriculture pages in en/hi/mr |
| RSS | agricultural news and advisories |
| JSON | open data APIs |
| Image | crop disease photos |
| Audio | farmer voice samples |
| Structured | soil, weather, market tables |

**Data Pipeline Stages:**
```
1. Source Discovery (allow-list check)
2. robots.txt + License validation
3. Download (with size limit, retry, checksum)
4. Unicode Normalization + Language Detection
5. PII Redaction
6. Toxicity/Safety Filter
7. Agriculture Relevance Scoring (classifier)
8. Deduplication (exact + near - MinHash)
9. Quality Scoring
10. Provenance Attachment (source_id, checksum, license)
11. Raw Write (MinIO immutable)
12. Curated Write (Iceberg/Parquet)
13. Quarantine on failure
```

**Temporal Workflow Design:**
```
IngestWorkflow -> CurationWorkflow -> IndexWorkflow
- ingest_web_workflow
- ingest_pdf_workflow
- curation_filter_workflow
- graph_build_workflow
```

**Lakehouse Tables:** `raw.documents`, `curated.documents`, `curated.chunks`, `curated.images`, `quarantine.records`, `manifests.datasets`, `manifests.models`, `telemetry.events`

**Exit Criteria:** Temporal ingestion workflow runs end-to-end, data lake writes immutable objects, every record has provenance, PII redaction passes safety tests, lakehouse manifest queryable.

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
| **M1 — Data Lake Ready** | Temporal ingestion, lakehouse, PII redaction, provenance, quarantine |
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

---

### 24. Immediate Next Actions

1. Create the monorepo with `uv workspace`
2. Add Docker Compose with Postgres, MinIO, Neo4j, Qdrant, Temporal, Redis
3. Implement kernel contracts (Query, Response, Citation, Safety)
4. Implement configuration validation (Pydantic Settings fail-loud)
5. Implement CI pipeline (lint, type, unit, import-linter, safety eval)
6. Create golden eval folder with 50 seed queries in en/hi/mr
7. Build first Temporal ingestion workflow (web + PDF)
8. Build first GraphRAG retrieval service
9. Build first LangGraph agent with safety fallback
10. Wire observability (OpenTelemetry + Prometheus + Grafana)

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
*Generated: AGRIMIND Implementation Plan v1.0 - 2026 Flagship Architecture*
*Owner: Principal AI Systems Architect*
