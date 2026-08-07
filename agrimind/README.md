# AGRIMIND — Autonomous Agricultural Intelligence Engine

**Flagship Production-Grade AI Platform for Agriculture**  
*Multilingual (English, Hindi, Marathi) | Offline-First | Self-Learning | GraphRAG-Powered*

---

## Overview

AGRIMIND is not a chatbot. It is a **self-improving agricultural intelligence engine** that continuously learns from data, farmer interactions, expert corrections, agronomy knowledge graphs, weather feeds, market feeds, satellite signals, and field feedback.

### Key Capabilities

- 🌾 **Multilingual QA** - Agricultural question answering in English, Hindi, and Marathi
- 🐛 **Disease Diagnosis** - Crop disease diagnosis from text and images
- 💊 **Safe Treatment Advice** - Pest/disease treatment with safety warnings and citations
- 🌦️ **Weather-Aware Advisory** - Location-specific weather guidance
- 📊 **Market Price Guidance** - Real-time market price information
- 🏛️ **Government Scheme Help** - Scheme eligibility and application guidance
- 📱 **Offline-First** - Works in rural areas with unstable connectivity
- 🗣️ **Voice-First UX** - Designed for low-literacy users
- 🔍 **Explainable Answers** - Every answer includes citations and confidence scores
- 🔄 **Self-Learning** - Automatically improves from feedback and failures

---

## Architecture

### Strict Layer Model

```
Layer 0: kernel          (contracts, config, errors, telemetry)
Layer 1: data-kernel     (lakehouse contracts, manifests)
Layer 2: memory          (graph, vector, retrieval)
Layer 3: models          (inference, tokenizer, registry)
Layer 4: agents          (LangGraph workflows, tools, safety)
Layer 5: services        (FastAPI microservices)
Layer 6: apps            (gateway, expert console, admin)
```

**Import Rules:** Lower layers can be imported by higher layers. Higher layers CANNOT import lower layers. No circular imports allowed.

### Core Services

| Service | Responsibility |
|---------|---------------|
| `gateway-service` | Authentication, rate limiting, routing |
| `assistant-api` | Farmer-facing chat/query endpoints |
| `agent-orchestrator` | LangGraph agent workflows |
| `memory-service` | GraphRAG + vector retrieval |
| `inference-service` | LLM serving (SGLang/vLLM) |
| `vision-service` | Crop disease image analysis |
| `feeds-service` | Weather, market, satellite feeds |
| `data-ingestion-service` | Source ingestion API |
| `curation-worker` | Temporal ETL/AI curation |
| `eval-service` | Golden set evaluation |
| `expert-console-api` | Human review and approvals |

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker & Docker Compose

### 1. Clone and Setup

```bash
cd agrimind

# Install all dependencies
uv sync --all-packages

# Copy environment configuration
cp .env.example .env
# Edit .env with your configuration
```

### 2. Start Infrastructure

```bash
# Start all infrastructure services
make up

# Verify services are healthy
docker compose ps
```

Required services:
- PostgreSQL (5432)
- MinIO (9000, 9001)
- Neo4j (7474, 7687)
- Qdrant (6333)
- Redis (6379)
- Temporal (7233, 8233)

### 3. Run Tests

```bash
# Run linting
make lint

# Run type checking
make type

# Run unit tests
make test

# Run all checks
make lint type test
```

### 4. Development Workflow

```bash
# Format code
make format

# Run specific test suite
uv run pytest tests/unit/test_contracts.py -v

# Clear caches
make clean
```

---

## Project Structure

```
agrimind/
├── pyproject.toml          # Root workspace config
├── Makefile                # Common commands
├── docker-compose.yml      # Local infrastructure
├── .env.example            # Environment template
├── README.md               # This file
├── ADRs/                   # Architecture Decision Records
│   └── 001-monorepo-layering.md
├── packages/               # Shared libraries (Layers 0-4)
│   ├── kernel/             # Layer 0: Core contracts
│   │   ├── contracts/      # Query, Response, Citation, Safety
│   │   ├── config/         # Pydantic settings
│   │   ├── errors/         # Custom exceptions
│   │   └── telemetry/      # Distributed tracing
│   ├── data-kernel/        # Layer 1: Data contracts
│   ├── memory/             # Layer 2: Retrieval
│   ├── models/             # Layer 3: Inference
│   ├── agents/             # Layer 4: Agent workflows
│   └── eval/               # Evaluation harness
├── services/               # Microservices (Layer 5)
│   ├── gateway-service/
│   ├── assistant-api/
│   ├── agent-orchestrator/
│   └── ...
├── workers/                # Background workers
│   ├── curation-worker/
│   └── training-orchestrator/
├── infra/                  # Infrastructure configs
│   ├── temporal/
│   └── k8s/
└── tests/                  # Test suites
    ├── unit/
    ├── contract/
    ├── integration/
    └── ...
```

---

## Phase 0 Status ✅

**Objective:** Create a clean, testable, reproducible monorepo foundation.

### Completed Items

- ✅ uv monorepo initialized
- ✅ ruff, mypy, pytest configured
- ✅ Pre-commit hooks setup
- ✅ Docker Compose with all infrastructure
- ✅ Environment configuration with validation
- ✅ Architecture Decision Records
- ✅ Kernel contracts (Query, Response, Citation, Safety)
- ✅ Configuration management (Pydantic Settings)
- ✅ Error handling hierarchy
- ✅ Distributed tracing foundation
- ✅ Unit tests for contracts
- ✅ Golden evaluation folder structure

### Validation Checklist

| Check | Command | Status |
|-------|---------|--------|
| Dependencies | `uv sync --all-packages` | ✅ Ready |
| Linting | `make lint` | ✅ Configured |
| Type Checking | `make type` | ✅ Configured |
| Unit Tests | `make test` | ✅ Passing |
| Infrastructure | `docker compose up -d` | ✅ Ready |
| Layer Enforcement | Import rules defined | ✅ Documented |

---

## Technology Stack

### Backend
- **Language:** Python 3.12+
- **Package Manager:** uv workspace
- **API Framework:** FastAPI
- **Validation:** Pydantic v2
- **Settings:** pydantic-settings
- **Async HTTP:** httpx
- **Logging:** structlog
- **Tracing:** OpenTelemetry
- **Metrics:** Prometheus
- **Dashboards:** Grafana

### AI Stack
- **Agent Orchestration:** LangGraph
- **Vector Embeddings:** BGE-Multilingual / Multilingual E5
- **Vector DB:** Qdrant
- **Graph DB:** Neo4j / FalkorDB
- **GraphRAG:** Ontology-based traversal + community summaries
- **Inference:** SGLang / vLLM
- **Edge:** ONNX Runtime / MLC-LLM
- **Training:** PyTorch, FSDP, LoRA/QLoRA, DPO

### Data Pipeline
- **Workflow:** Temporal
- **Object Storage:** MinIO / S3
- **Lakehouse:** Apache Iceberg / Parquet
- **Query Engine:** DuckDB / Polars
- **Metadata:** PostgreSQL

---

## Design Principles

### Product Principles
1. **Farmer Safety First** - Never hallucinate chemical dosage or treatment
2. **Local Language First** - Marathi and Hindi are first-class citizens
3. **Offline-First** - Edge inference works without internet
4. **Explainable Answers** - Citations and confidence for every answer
5. **Continuous Learning** - Learn from feedback and failures
6. **Human-in-the-Loop** - Unsafe changes require approval

### Engineering Principles
1. **Strict Layering** - No import cycles between layers
2. **Contract-First** - Typed contracts for all service communication
3. **Fail Loud** - Missing config or bad schema fails immediately
4. **Deterministic Rebuild** - Reproducible artifacts
5. **Test-Driven AI** - Eval harnesses before features
6. **Observability by Default** - Trace every request

### AI Principles
1. **Grounded Generation** - Based on retrieved evidence
2. **Epistemic Awareness** - Know when uncertain
3. **Data-Centric Improvement** - Fix root causes
4. **Eval-Gated Deployment** - No regressions to production
5. **Safe Autonomy** - Automatic improvements with gates

---

## Next Phases

### Phase 1: Kernel Contracts and Configuration
Freeze all core contracts, implement configuration validation, add Request ID middleware.

### Phase 2: Data Acquisition Plane
Build Temporal ingestion workflows, lakehouse storage, PII redaction, relevance scoring.

### Phase 3: Knowledge Graph and GraphRAG
Define ontology, build entity extraction, implement GraphRAG retrieval.

### Phase 4: Model Factory
Tokenizer manifests, model registry, LoRA fine-tuning pipeline, ONNX export.

### Phase 5: Retrieval and Memory Service
Hybrid retrieval (graph + vector), semantic cache, citation enforcement.

### Phase 6: Agent Orchestrator and Safety Engine
LangGraph workflows, tool planning, safety policy engine, confidence gates.

### Phase 7: Inference Service and Edge-Cloud Continuum
Cloud inference (vLLM/SGLang), edge inference (ONNX), model router.

### Phase 8: Autonomous Self-Learning Flywheel
Feedback collection, failure taxonomy, synthetic data generation, canary deployment.

### Phase 9: Expert Console and Human-in-the-Loop
Review interface, approval workflows, audit logging.

### Phase 10: Production Hardening
Security, reliability, observability, backup/restore drills.

---

## Contributing

### Setting Up Pre-Commit Hooks

```bash
pip install pre-commit
pre-commit install
```

### Running CI Checks Locally

```bash
make lint type test
```

### Adding New Packages

```bash
uv workspace add packages/my-new-package
```

---

## License

[Specify License]

---

## Contact

For questions about AGRIMIND architecture or implementation, please refer to the Architecture Decision Records (ADRs) or contact the Principal AI Systems Architect.

---

*Generated from AGRIMIND Implementation Plan v1.0 - 2026 Flagship Architecture*
