"""Feeds service — weather / market connectors."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from agents.tools.market import MarketTool
from agents.tools.weather import WeatherTool

logger = structlog.get_logger()
weather = WeatherTool()
market = MarketTool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("feeds-service starting")
    yield


app = FastAPI(title="feeds-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "feeds-service", "mode": "stub-connectors"}


@app.get("/v1/weather/{district}")
async def get_weather(district: str):
    return await weather.get(district)


@app.get("/v1/market/{crop}")
async def get_market(crop: str, market_name: str = "Pune"):
    return await market.get_price(crop, market_name)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
