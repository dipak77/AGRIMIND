"""Weather tool — stub with honest source label (replace with IMD/OpenWeather)."""

from __future__ import annotations


class WeatherTool:
    async def get(self, district: str) -> dict:
        return {
            "district": district,
            "forecast": "Light rain possible next 2 days; avoid spraying if wet foliage.",
            "source": "weather-stub",
            "disclaimer": "Not a live IMD feed; configure OPENWEATHER_API_KEY for production.",
        }
