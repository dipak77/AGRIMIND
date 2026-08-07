"""expert-console-api - Main FastAPI Application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("expert-console-api starting up")
    yield
    logger.info("expert-console-api shutting down")

app = FastAPI(title="expert-console-api", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "expert-console-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
