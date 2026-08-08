"""Market price tool — stub with honest source label (replace with Agmarknet)."""

from __future__ import annotations


class MarketTool:
    async def get_price(self, crop: str, market: str = "Pune") -> dict:
        return {
            "crop": crop,
            "market": market,
            "price": "Rs 7200/quintal",
            "trend": "stable",
            "source": "market-stub",
            "disclaimer": "Not a live Agmarknet feed; configure AGMARKNET_API_KEY for production.",
        }
