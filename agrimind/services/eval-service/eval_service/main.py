"""Eval service — trigger golden harness."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

logger = structlog.get_logger()


class EvalReq(BaseModel):
    dataset: str = "packages/eval/golden/en"
    threshold: float = 0.5


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("eval-service starting")
    yield


app = FastAPI(title="eval-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "eval-service"}


@app.post("/v1/run")
async def run_eval(req: EvalReq):
    try:
        from eval.harness.run import run

        ok = run(req.dataset, req.threshold)
        return {"passed": ok, "dataset": req.dataset, "threshold": req.threshold}
    except Exception as exc:  # pragma: no cover
        logger.exception("eval_failed")
        return {"passed": False, "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
