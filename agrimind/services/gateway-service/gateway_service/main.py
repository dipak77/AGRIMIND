"""Gateway Service - Main FastAPI Application."""
import uuid
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import jwt
import structlog
from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.telemetry.tracing import TraceContext

logger = structlog.get_logger()
settings = get_settings()


def generate_request_id() -> str:
    return str(uuid.uuid4())


async def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.security.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Gateway service starting up")
    yield
    logger.info("Gateway service shutting down")


app = FastAPI(title="AGRIMIND Gateway", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", generate_request_id())
    trace_ctx = TraceContext(request_id=request_id, span_id=str(uuid.uuid4()))
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    logger.info(
        "request_processed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration * 1000,
        request_id=request_id,
    )
    
    return response


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "gateway"}


@app.get("/ready")
async def readiness_check():
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
