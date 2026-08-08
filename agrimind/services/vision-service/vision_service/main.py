"""Vision service — crop disease image analysis (stub model)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, File, UploadFile

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("vision-service starting")
    yield


app = FastAPI(title="vision-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vision-service", "mode": "stub"}


@app.post("/v1/diagnose")
async def diagnose(file: UploadFile = File(...)):
    # Stub: always returns a placeholder diagnosis with honest labels
    _ = await file.read()
    return {
        "disease": "possible_leaf_stress",
        "confidence": 0.55,
        "simulated": True,
        "symptoms": ["discoloration", "spots"],
        "advice": "Upload quality field photos and use expert review; model not trained yet.",
        "citation": {
            "source_id": "vision_stub",
            "source_type": "model",
            "note": "Not a production vision model",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
