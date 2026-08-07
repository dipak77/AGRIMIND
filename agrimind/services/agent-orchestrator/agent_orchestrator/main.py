"""Agent Orchestrator - Main FastAPI Application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("agent-orchestrator starting up")
    yield
    logger.info("agent-orchestrator shutting down")

app = FastAPI(title="agent-orchestrator", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "agent-orchestrator"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
