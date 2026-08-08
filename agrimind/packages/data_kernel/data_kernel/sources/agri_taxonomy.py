"""Agriculture + farmer domain taxonomy: categories and discovery keywords.

Used by the online source discovery helper to search trusted open providers
(Wikipedia, Open Library, Internet Archive, FAO/ICAR patterns) without
generic web crawl noise.
"""

from __future__ import annotations

from typing import Any

# Category id → human label + multilingual keywords (EN primary, HI/MR hints).
AGRI_CATEGORIES: dict[str, dict[str, Any]] = {
    "crops": {
        "label": "Crops & cultivation",
        "keywords": [
            "crop production",
            "crop rotation",
            "wheat cultivation",
            "rice paddy farming",
            "cotton farming",
            "millet sorghum",
            "maize corn cultivation",
            "pulse legumes farming",
            "oilseed mustard soybean",
            "sugarcane cultivation",
        ],
    },
    "soil_health": {
        "label": "Soil health & fertility",
        "keywords": [
            "soil health",
            "soil fertility",
            "soil organic carbon",
            "soil testing",
            "erosion control agriculture",
            "compost manure farmyard",
            "cover crops soil",
            "salinity sodicity soil",
        ],
    },
    "irrigation_water": {
        "label": "Irrigation & water",
        "keywords": [
            "irrigation agriculture",
            "drip irrigation",
            "sprinkler irrigation",
            "watershed management",
            "groundwater irrigation",
            "canal irrigation India",
            "water use efficiency farming",
            "rainwater harvesting agriculture",
        ],
    },
    "pests_ipm": {
        "label": "Pests, disease & IPM",
        "keywords": [
            "integrated pest management",
            "crop pest control",
            "plant disease agriculture",
            "biological control pest",
            "bollworm cotton",
            "fungicide agriculture safe use",
            "nematode plant pathology",
            "locust control agriculture",
        ],
    },
    "fertilizers_nutrients": {
        "label": "Fertilizers & plant nutrition",
        "keywords": [
            "fertilizer recommendation",
            "nitrogen phosphorus potassium crop",
            "micronutrient deficiency plants",
            "organic fertilizer compost",
            "biofertilizer rhizobium",
            "nutrient management agriculture",
            "leaf color chart nitrogen",
        ],
    },
    "seeds_varieties": {
        "label": "Seeds & varieties",
        "keywords": [
            "seed production agriculture",
            "crop variety breeding",
            "hybrid seed farmers",
            "seed treatment agriculture",
            "germplasm plant genetic resources",
            "certified seed India",
        ],
    },
    "organic_farming": {
        "label": "Organic & natural farming",
        "keywords": [
            "organic farming",
            "natural farming India",
            "zero budget natural farming",
            "biodynamic agriculture",
            "organic certification agriculture",
            "agroecology farming",
        ],
    },
    "livestock": {
        "label": "Livestock & animal husbandry",
        "keywords": [
            "livestock management",
            "cattle dairy farming",
            "goat sheep rearing",
            "poultry farming",
            "animal nutrition fodder",
            "veterinary public health livestock",
            "pasture grazing management",
        ],
    },
    "dairy": {
        "label": "Dairy",
        "keywords": [
            "dairy farming",
            "milk production cooperative",
            "cattle breed dairy",
            "fodder crop dairy",
            "milk quality hygiene",
        ],
    },
    "horticulture": {
        "label": "Horticulture & fruits/vegetables",
        "keywords": [
            "horticulture farming",
            "vegetable cultivation",
            "fruit orchard management",
            "protected cultivation greenhouse",
            "floriculture India",
            "post harvest vegetables",
        ],
    },
    "fisheries_aquaculture": {
        "label": "Fisheries & aquaculture",
        "keywords": [
            "aquaculture farming",
            "fish pond culture",
            "shrimp farming",
            "inland fisheries India",
            "feed management aquaculture",
        ],
    },
    "climate_weather": {
        "label": "Climate, weather & resilience",
        "keywords": [
            "climate smart agriculture",
            "drought resistant crops",
            "weather advisory farmers",
            "flood agriculture risk",
            "heat stress crops",
            "agro meteorology",
        ],
    },
    "mechanization": {
        "label": "Farm mechanization",
        "keywords": [
            "farm mechanization",
            "tractor agriculture",
            "combine harvester",
            "precision agriculture machinery",
            "custom hiring center farm",
        ],
    },
    "post_harvest": {
        "label": "Post-harvest & storage",
        "keywords": [
            "post harvest technology",
            "grain storage farmers",
            "cold chain horticulture",
            "food processing agriculture",
            "warehouse receipt agriculture",
        ],
    },
    "markets_prices": {
        "label": "Markets & prices",
        "keywords": [
            "agricultural marketing",
            "mandi price India",
            "commodity price agriculture",
            "farmer producer organization",
            "supply chain agriculture",
            "minimum support price MSP",
        ],
    },
    "policy_schemes": {
        "label": "Policy, schemes & extension",
        "keywords": [
            "agricultural extension services",
            "farmer scheme India",
            "PM Kisan scheme",
            "crop insurance PMFBY",
            "Krishi Vigyan Kendra",
            "agricultural policy India",
            "subsidy fertilizer farmers",
        ],
    },
    "farmer_livelihood": {
        "label": "Farmer livelihood & advisory",
        "keywords": [
            "farmer advisory services",
            "smallholder farming",
            "women in agriculture",
            "rural livelihood agriculture",
            "farm income diversification",
            "farmer training extension",
        ],
    },
    "sustainable_agri": {
        "label": "Sustainable & regenerative agri",
        "keywords": [
            "sustainable agriculture",
            "regenerative agriculture",
            "conservation agriculture",
            "agroforestry farming",
            "integrated farming system",
            "carbon farming agriculture",
        ],
    },
    "plant_protection_chemicals": {
        "label": "Safe pesticide use",
        "keywords": [
            "pesticide safe use farmers",
            "integrated disease management",
            "herbicide resistance agriculture",
            "pesticide residue food safety",
        ],
    },
    "agri_books_reference": {
        "label": "Agri textbooks & reference books",
        "keywords": [
            "agriculture textbook",
            "handbook of agriculture",
            "soil science textbook",
            "plant pathology book",
            "agronomy textbook free",
            "farmers of forty centuries",
            "how to feed the world agriculture",
            "FAO agricultural publication",
        ],
    },
}


# Default keyword packs used when the client sends no free-text query.
DEFAULT_DISCOVERY_KEYWORDS: list[str] = [
    "agriculture",
    "farming",
    "crop production",
    "soil health",
    "irrigation",
    "integrated pest management",
    "organic farming",
    "livestock",
    "horticulture",
    "climate smart agriculture",
    "agricultural extension",
    "farmer advisory",
]


def list_categories() -> list[dict[str, Any]]:
    """Return category metadata for UI / API."""
    out: list[dict[str, Any]] = []
    for cid, meta in AGRI_CATEGORIES.items():
        kws = list(meta.get("keywords") or [])
        out.append(
            {
                "id": cid,
                "label": meta.get("label") or cid,
                "keyword_count": len(kws),
                "keywords": kws,
            }
        )
    return out


def keywords_for_categories(
    category_ids: list[str] | None = None,
    *,
    extra_keywords: list[str] | None = None,
    limit_per_category: int = 6,
) -> list[str]:
    """Flatten unique keywords for selected categories (+ optional free-text)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(k: str) -> None:
        t = " ".join((k or "").split()).strip().lower()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    if extra_keywords:
        for k in extra_keywords:
            add(k)

    ids = category_ids or list(AGRI_CATEGORIES.keys())
    for cid in ids:
        meta = AGRI_CATEGORIES.get(cid)
        if not meta:
            continue
        for k in (meta.get("keywords") or [])[: max(1, limit_per_category)]:
            add(str(k))

    if not out:
        for k in DEFAULT_DISCOVERY_KEYWORDS:
            add(k)
    return out


def match_categories(text: str) -> list[str]:
    """Heuristic category tags for a title/snippet."""
    t = (text or "").lower()
    hits: list[str] = []
    for cid, meta in AGRI_CATEGORIES.items():
        for k in meta.get("keywords") or []:
            # use first 2 tokens of keyword for softer match
            token = " ".join(str(k).lower().split()[:2])
            if token and token in t:
                hits.append(cid)
                break
    return hits
