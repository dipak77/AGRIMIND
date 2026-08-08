"""Default knowledge-graph seed: Crop ↔ Pest ↔ Practice/Treatment with provenance."""

from __future__ import annotations

from typing import Any


def default_graph_nodes() -> list[dict[str, Any]]:
    return [
        {
            "id": "crop:cotton",
            "type": "Crop",
            "name": "Cotton",
            "aliases": ["cotton", "कपास", "कापूस", "kapas", "kapus"],
            "source_id": "src_icar_cotton_ipm_001",
            "is_approved": True,
        },
        {
            "id": "pest:bollworm",
            "type": "Pest",
            "name": "Bollworm",
            "aliases": ["bollworm", "helicoverpa", "बोंडअळी", "सुंडी", "ballworm"],
            "source_id": "src_icar_cotton_ipm_001",
            "is_approved": True,
        },
        {
            "id": "practice:ipm",
            "type": "Practice",
            "name": "Integrated Pest Management",
            "aliases": ["ipm", "integrated pest management", "एकात्मिक कीड व्यवस्थापन"],
            "source_id": "src_icar_cotton_ipm_001",
            "is_approved": True,
            "description": "Monitoring, pheromone traps, cultural controls, approved products only.",
        },
        {
            "id": "treatment:neem",
            "type": "Treatment",
            "name": "Neem-based products",
            "aliases": ["neem", "azadirachtin", "नीम"],
            "source_id": "src_icar_cotton_ipm_001",
            "is_approved": True,
            "safety_critical": True,
        },
        {
            "id": "practice:crop_rotation",
            "type": "Practice",
            "name": "Crop Rotation",
            "aliases": ["crop rotation", "फसल चक्र", "पीक फेरपालट"],
            "source_id": "src_crop_rotation_001",
            "is_approved": True,
            "description": "Rotate legumes with cereals to improve soil and break pest cycles.",
        },
        {
            "id": "crop:generic_cereals",
            "type": "Crop",
            "name": "Cereals",
            "aliases": ["cereal", "wheat", "rice", "ज्वारी", "गहू"],
            "source_id": "src_crop_rotation_001",
            "is_approved": True,
        },
        {
            "id": "scheme:pmkisan",
            "type": "GovernmentScheme",
            "name": "PM-KISAN",
            "aliases": ["pm-kisan", "pmkisan", "योजना"],
            "source_id": "src_scheme_pmkisan_001",
            "is_approved": True,
        },
        {
            "id": "chemical:monocrotophos",
            "type": "Chemical",
            "name": "Monocrotophos",
            "aliases": ["monocrotophos"],
            "source_id": "src_safety_banned_001",
            "is_approved": False,
            "banned": True,
            "safety_critical": True,
        },
    ]


def default_graph_edges() -> list[dict[str, Any]]:
    """Edges carry provenance; high-risk edges require is_approved=True to surface."""
    return [
        {
            "source": "crop:cotton",
            "target": "pest:bollworm",
            "relation": "AFFECTED_BY",
            "source_id": "src_icar_cotton_ipm_001",
            "confidence": 0.92,
            "is_approved": True,
            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
            "checksum": "sha256:seed-cotton-ipm",
            "span": "Bollworm host association",
        },
        {
            "source": "pest:bollworm",
            "target": "practice:ipm",
            "relation": "MANAGED_BY",
            "source_id": "src_icar_cotton_ipm_001",
            "confidence": 0.9,
            "is_approved": True,
            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
            "checksum": "sha256:seed-cotton-ipm",
            "span": "IPM management",
        },
        {
            "source": "pest:bollworm",
            "target": "treatment:neem",
            "relation": "TREATED_BY",
            "source_id": "src_icar_cotton_ipm_001",
            "confidence": 0.85,
            "is_approved": True,
            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
            "checksum": "sha256:seed-cotton-ipm",
            "span": "Neem treatment option",
            "safety_critical": True,
        },
        {
            "source": "crop:cotton",
            "target": "practice:ipm",
            "relation": "REQUIRES",
            "source_id": "src_icar_cotton_ipm_001",
            "confidence": 0.88,
            "is_approved": True,
            "url_or_path": "s3://agrimind-curated/icar/cotton-ipm.pdf",
            "checksum": "sha256:seed-cotton-ipm",
            "span": "Crop IPM requirement",
        },
        {
            "source": "crop:generic_cereals",
            "target": "practice:crop_rotation",
            "relation": "REQUIRES",
            "source_id": "src_crop_rotation_001",
            "confidence": 0.87,
            "is_approved": True,
            "url_or_path": "s3://agrimind-curated/agronomy/crop-rotation.pdf",
            "checksum": "sha256:seed-rotation",
            "span": "Rotation practice",
        },
        # Explicit non-recommendation edge (banned chemical) — must NOT be surfaced as treatment
        {
            "source": "pest:bollworm",
            "target": "chemical:monocrotophos",
            "relation": "TREATED_BY",
            "source_id": "src_safety_banned_001",
            "confidence": 0.99,
            "is_approved": False,
            "banned": True,
            "url_or_path": "s3://agrimind-curated/safety/banned-list.pdf",
            "checksum": "sha256:seed-banned",
            "span": "Banned — do not recommend",
            "safety_critical": True,
        },
    ]
