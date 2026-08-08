"""Admin service — tenants, sources, kill switches (minimal)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

logger = structlog.get_logger()

_STATE = {"kill_switch": False, "sources_allow_list": ["icar.org.in", "gov.in"]}


class KillSwitch(BaseModel):
    enabled: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("admin-service starting")
    yield


app = FastAPI(title="admin-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-service"}


@app.get("/v1/status")
async def status():
    return dict(_STATE)


@app.post("/v1/kill-switch")
async def set_kill_switch(body: KillSwitch):
    _STATE["kill_switch"] = body.enabled
    return {"kill_switch": _STATE["kill_switch"]}


@app.get("/v1/sources")
async def sources():
    return {"allow_list": _STATE["sources_allow_list"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
