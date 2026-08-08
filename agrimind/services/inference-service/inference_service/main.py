"""Inference service — registry-gated serving with sim or vLLM/SGLang backend (Phase D).

Environment (see also ``infra/vllm/README.md`` and root ``.env.example``):

- ``INFERENCE_MODE``: ``auto`` | ``sim`` | ``remote``
  - ``auto`` — OpenAI-compat remote if ``VLLM_BASE_URL`` set, else grounded sim
  - ``remote`` — require ``VLLM_BASE_URL`` (real vLLM/SGLang)
  - ``sim`` — always grounded sim (no GPU)
- ``VLLM_BASE_URL`` / ``INFERENCE_REMOTE_URL``: OpenAI base, e.g. ``http://localhost:8008/v1``
- ``VLLM_API_KEY``: Bearer token for vLLM (default ``EMPTY``)
- ``DEFAULT_CLOUD_MODEL``: model id passed to the backend (should match vLLM ``--model``)
- ``MODEL_REGISTRY_PATH`` / ``MODEL_REGISTRY_LOCAL``: model manifests
- ``INFERENCE_REQUIRE_REGISTRY``: if true, refuse unknown models

GPU packaging (weights not bundled)::

    docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu up -d vllm
    INFERENCE_MODE=remote VLLM_BASE_URL=http://localhost:8008/v1 VLLM_API_KEY=EMPTY
"""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agrimind_kernel.config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Ensure flat models package imports (inference/, registry/, tokenizer/)
_MODELS_ROOT = Path(__file__).resolve().parents[2] / "packages" / "models"
if _MODELS_ROOT.exists() and str(_MODELS_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODELS_ROOT))


def _registry_path() -> Path:
    raw = os.getenv("MODEL_REGISTRY_PATH", getattr(settings, "model_registry_path", "./data/model-registry"))
    if raw.startswith("s3://"):
        # local filesystem mirror for manifests
        return Path(os.getenv("MODEL_REGISTRY_LOCAL", "./data/model-registry"))
    return Path(raw)


def _build_engine():
    from inference.engine import InferenceEngine
    from registry.client import ModelRegistryClient

    registry = ModelRegistryClient(_registry_path())
    registry.ensure_seed_defaults()
    mode = os.getenv("INFERENCE_MODE", getattr(settings, "inference_mode", "auto"))
    vllm_url = os.getenv("VLLM_BASE_URL") or os.getenv("INFERENCE_REMOTE_URL") or getattr(
        settings, "vllm_base_url", None
    )
    api_key = os.getenv("VLLM_API_KEY", "EMPTY")
    model_id = os.getenv("DEFAULT_CLOUD_MODEL", settings.default_cloud_model)
    require_registry = os.getenv("INFERENCE_REQUIRE_REGISTRY", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    if (mode or "auto").lower() == "remote" and not vllm_url:
        logger.error(
            "INFERENCE_MODE=remote but VLLM_BASE_URL / INFERENCE_REMOTE_URL unset",
            mode=mode,
        )
    elif vllm_url:
        logger.info(
            "inference remote backend configured",
            mode=mode,
            vllm_base_url=vllm_url,
            default_model=model_id,
        )
    else:
        logger.info(
            "inference using grounded sim backend (no VLLM_BASE_URL)",
            mode=mode,
            default_model=model_id,
        )
    return InferenceEngine.from_settings(
        model_id=model_id,
        mode=mode,
        vllm_base_url=vllm_url or None,
        vllm_api_key=api_key,
        registry=registry,
        require_registry=require_registry,
    ), registry


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model_id: str | None = None
    max_tokens: int = 512
    temperature: float = 0.2
    intent: str | None = None
    lang: str | None = None
    evidence: str | None = None


class GenerateResponse(BaseModel):
    request_id: str
    model_id: str
    completion: str
    finish_reason: str = "stop"
    usage: dict
    latency_ms: float
    simulated: bool = True
    intent: str | None = None
    backend: str | None = None
    warnings: list[str] | None = None


class PromoteRequest(BaseModel):
    model_id: str
    target_status: str = "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from registry.canary import CanaryController

    engine, registry = _build_engine()
    app.state.engine = engine
    app.state.registry = registry
    app.state.canary = CanaryController(
        registry,
        state_path=os.getenv(
            "CANARY_STATE_PATH",
            str(_registry_path() / "canary_state.json"),
        ),
    )
    # seed production pointer to default sim model if empty
    if not app.state.canary.state.production_model_id:
        try:
            app.state.canary.set_production(engine.model_id)
        except Exception:
            pass
    logger.info(
        "inference-service starting",
        model=engine.model_id,
        backend=engine.backend_name,
        simulated=engine.simulated,
        remote_endpoint=getattr(engine, "endpoint", "") or None,
        registry=str(_registry_path()),
    )
    if engine.simulated:
        logger.info(
            "backend is simulated — set INFERENCE_MODE=remote and VLLM_BASE_URL "
            "for real vLLM (see infra/vllm/README.md)"
        )
    yield


app = FastAPI(title="inference-service", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health():
    engine = app.state.engine
    return {
        "status": "healthy",
        "service": "inference-service",
        "model": engine.model_id,
        "backend": engine.backend_name,
        "mode": "simulated" if engine.simulated else "remote",
        "backend_ok": engine.health_check(),
    }


@app.get("/ready")
async def ready():
    engine = app.state.engine
    ok = engine.health_check()
    if not ok and not engine.simulated:
        raise HTTPException(status_code=503, detail="remote backend unhealthy")
    return {
        "status": "ready",
        "backend": engine.backend_name,
        "simulated": engine.simulated,
    }


@app.get("/v1/models")
async def list_models():
    registry = app.state.registry
    models = [m.model_dump(mode="json") for m in registry.list_models()]
    return {"count": len(models), "models": models}


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    from inference.contracts import InferenceRequest
    from registry.gates import GateError

    engine = app.state.engine
    # E3: optional canary traffic split when client does not pin model_id
    if req.model_id:
        model_id = req.model_id
    else:
        model_id = app.state.canary.choose_model(engine.model_id)
    ireq = InferenceRequest(
        model_id=model_id,
        prompt=req.prompt,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    try:
        resp = await engine.generate(
            ireq,
            intent=req.intent or "general_advisory",
            lang=req.lang or "en",
            evidence=req.evidence or "",
        )
    except GateError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("generate_failed")
        raise HTTPException(status_code=502, detail=f"inference failed: {exc}") from exc

    return GenerateResponse(
        request_id=resp.request_id,
        model_id=resp.model_id,
        completion=resp.completion,
        finish_reason=resp.finish_reason,
        usage=resp.usage,
        latency_ms=resp.latency_ms,
        simulated=engine.simulated,
        intent=req.intent,
        backend=engine.backend_name,
        warnings=resp.warnings,
    )


@app.post("/v1/models/promote")
async def promote_model(req: PromoteRequest):
    """D3: promote only if eval thresholds pass."""
    from registry.gates import GateError

    registry = app.state.registry
    try:
        updated = registry.promote_model(req.model_id, req.target_status)
    except GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "promoted", "model": updated.model_dump(mode="json")}


class CanaryStart(BaseModel):
    model_id: str
    traffic_pct: int = 10


class CanaryEval(BaseModel):
    canary_scores: dict
    production_scores: dict | None = None
    max_faithfulness_drop: float = 0.05


@app.get("/v1/canary")
async def canary_status():
    return app.state.canary.state.to_dict()


@app.post("/v1/canary/start")
async def canary_start(body: CanaryStart):
    from registry.gates import GateError

    try:
        state = app.state.canary.start_canary(body.model_id, body.traffic_pct)
    except GateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "canary_started", "state": state.to_dict()}


@app.post("/v1/canary/evaluate")
async def canary_evaluate(body: CanaryEval):
    """E3: regression check → auto-rollback if canary worse."""
    result = app.state.canary.evaluate_canary_and_maybe_rollback(
        body.canary_scores,
        production_scores=body.production_scores,
        max_faithfulness_drop=body.max_faithfulness_drop,
    )
    return {
        "rolled_back": result.rolled_back,
        "reason": result.reason,
        "active_production": result.active_production,
        "state": result.state,
    }


@app.post("/v1/canary/promote")
async def canary_promote():
    try:
        state = app.state.canary.promote_canary_to_production()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "promoted", "state": state.to_dict()}


@app.post("/v1/canary/rollback")
async def canary_rollback(reason: str = "manual"):
    result = app.state.canary.rollback(reason=reason)
    return {
        "rolled_back": result.rolled_back,
        "reason": result.reason,
        "active_production": result.active_production,
        "state": result.state,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
