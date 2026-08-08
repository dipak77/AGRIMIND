.PHONY: sync lint type test up down eval eval-retrieval critical-path clean vllm-up vllm-down vllm-smoke

sync:
	uv sync --all-packages

# Align with .github/workflows/ci.yml (offline; no Docker deps)
lint:
	uv run ruff check packages/agrimind-kernel packages/agents packages/memory packages/data_kernel services tests --ignore RUF012,B017,B008

format:
	uv run ruff check --fix packages/agrimind-kernel packages/agents packages/memory packages/data_kernel services tests --ignore RUF012,B017,B008
	uv run ruff format packages/agrimind-kernel packages/agents packages/memory packages/data_kernel services tests

type:
	uv run mypy packages/agrimind-kernel/agrimind_kernel --ignore-missing-imports || true

test:
	uv run pytest tests/unit tests/contract tests/retrieval -q --tb=short

# Phase F load / SLO checks (offline)
load:
	uv run pytest tests/load -q --tb=short

up:
	docker compose up -d

down:
	docker compose down -v

logs:
	docker compose logs -f

# ---------------------------------------------------------------------------
# GPU vLLM (optional — does not run with plain `make up`)
# Requires NVIDIA GPU + nvidia-container-toolkit. Docs: infra/vllm/README.md
# Windows: use the docker compose lines below (Make may lack bash).
# ---------------------------------------------------------------------------
vllm-up:
	docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu up -d vllm

vllm-down:
	docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu stop vllm
	docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu rm -f vllm

vllm-smoke:
	@# bash smoke; on Windows run: .\scripts\smoke_vllm.ps1
	bash scripts/smoke_vllm.sh

eval:
	uv run python -m eval.harness.run --dataset packages/eval/golden/en --threshold 0.5

# Offline golden retrieval (B4): in-memory graph + fake vector; p95 budget 300ms
eval-retrieval:
	uv run python -m eval.harness.retrieval_run --dataset packages/eval/golden/retrieval --budget-ms 300

# Phase D: block bad model promotion (exit 2 if blocked)
promotion-gate:
	uv run python -m eval.harness.promotion_gate --registry ./data/model-registry --model-id agrimind-7b-sim-v0.1.0

# Phase C data plane (local pipeline, no Temporal required)
ingest-local:
	@echo "POST /v1/ingest mode=local — start: uv run uvicorn data_ingestion_service.main:app --app-dir services/data-ingestion-service --port 8007"

# Local critical path without Docker (memory+inference+orchestrator+assistant+gateway)
critical-path:
	@echo "Start in 5 terminals (A3/A4 HTTP boundaries):"
	@echo "  uv run uvicorn memory_service.main:app --app-dir services/memory-service --port 8003"
	@echo "  uv run uvicorn inference_service.main:app --app-dir services/inference-service --port 8004"
	@echo "  uv run uvicorn agent_orchestrator.main:app --app-dir services/agent-orchestrator --port 8002"
	@echo "  uv run uvicorn assistant_api.main:app --app-dir services/assistant-api --port 8001"
	@echo "  uv run uvicorn gateway_service.main:app --app-dir services/gateway-service --port 8000"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
