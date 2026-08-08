"""Default agricultural evidence chunks for local Qdrant bootstrap."""

from __future__ import annotations

from typing import Any


def default_seed_documents() -> list[dict[str, Any]]:
    """Curated stub-to-live seed set (En + a few Hi/Mr aliases in text)."""
    return [
        {
            "doc_id": "src_icar_cotton_ipm_001",
            "text": (
                "For cotton bollworm (Helicoverpa): use IPM — field monitoring, "
                "pheromone traps, neem-based products, and approved chemicals only "
                "with agronomist guidance. Banned chemicals must not be recommended. "
                "कपाशी बोंडअळी / कपास की बॉलवर्म।"
            ),
            "title": "ICAR Cotton IPM Advisory",
            "source_id": "src_icar_cotton_ipm_001",
            "source_type": "document",
            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
            "checksum": "sha256:seed-cotton-ipm",
            "lang": "en",
            "span": "Bollworm IPM",
        },
        {
            "doc_id": "src_crop_rotation_001",
            "text": (
                "Crop rotation improves soil health, breaks pest cycles, and reduces "
                "fertilizer dependency. Rotate legumes with cereals. "
                "फसल चक्र / पीक फेरपालट."
            ),
            "title": "Crop Rotation Basics",
            "source_id": "src_crop_rotation_001",
            "source_type": "document",
            "url_or_path": "s3://agrimind-curated/agronomy/crop-rotation.pdf",
            "checksum": "sha256:seed-rotation",
            "lang": "en",
            "span": "Rotation benefits",
        },
        {
            "doc_id": "src_weather_spray_001",
            "text": (
                "Avoid pesticide spraying before heavy rain; wash-off reduces efficacy "
                "and increases runoff risk. Check local forecast (हवामान / मौसम)."
            ),
            "title": "Weather-aware spraying",
            "source_id": "src_weather_spray_001",
            "source_type": "document",
            "url_or_path": "s3://agrimind-curated/weather/spray-guidance.pdf",
            "checksum": "sha256:seed-weather",
            "lang": "en",
            "span": "Rain and spray",
        },
        {
            "doc_id": "src_market_cotton_001",
            "text": (
                "Cotton mandi prices vary by grade and location. Compare nearby markets "
                "(Agmarknet) before selling. कापूस बाजार भाव / कपास मंडी।"
            ),
            "title": "Cotton market guidance",
            "source_id": "src_market_cotton_001",
            "source_type": "api",
            "url_or_path": "https://agmarknet.gov.in/",
            "checksum": "sha256:seed-market",
            "lang": "en",
            "span": "Price discovery",
        },
        {
            "doc_id": "src_scheme_pmkisan_001",
            "text": (
                "Government scheme eligibility (e.g. PM-KISAN) should be verified with "
                "local agriculture office or official portals. योजना / अनुदान."
            ),
            "title": "Scheme eligibility note",
            "source_id": "src_scheme_pmkisan_001",
            "source_type": "document",
            "url_or_path": "s3://agrimind-curated/schemes/pmkisan.pdf",
            "checksum": "sha256:seed-scheme",
            "lang": "en",
            "span": "Eligibility",
        },
        {
            "doc_id": "src_safety_banned_001",
            "text": (
                "Never recommend banned pesticides such as DDT, monocrotophos, endosulfan. "
                "Always require verified dosage sources and KVK consultation for chemicals."
            ),
            "title": "Banned chemicals safety",
            "source_id": "src_safety_banned_001",
            "source_type": "document",
            "url_or_path": "s3://agrimind-curated/safety/banned-list.pdf",
            "checksum": "sha256:seed-banned",
            "lang": "en",
            "span": "Banned list",
        },
    ]
