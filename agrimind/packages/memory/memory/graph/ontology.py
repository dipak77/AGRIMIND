"""Agricultural Knowledge Graph Ontology."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class NodeType(str, Enum):
    CROP = "Crop"
    DISEASE = "Disease"
    PEST = "Pest"
    CHEMICAL = "Chemical"
    FERTILIZER = "Fertilizer"
    SYMPTOM = "Symptom"
    TREATMENT = "Treatment"
    DOSAGE = "Dosage"
    SOIL_TYPE = "SoilType"
    WEATHER_CONDITION = "WeatherCondition"
    SEASON = "Season"
    GOVERNMENT_SCHEME = "GovernmentScheme"
    MARKET = "Market"
    LOCATION = "Location"
    VARIETY = "Variety"
    PRACTICE = "Practice"
    ALIAS_EN = "AliasEn"
    ALIAS_HI = "AliasHi"
    ALIAS_MR = "AliasMr"


class RelationshipType(str, Enum):
    AFFECTED_BY = "AFFECTED_BY"
    HAS_SYMPTOM = "HAS_SYMPTOM"
    TREATED_BY = "TREATED_BY"
    CAUSES = "CAUSES"
    HAS_DOSAGE = "HAS_DOSAGE"
    CONTAINS = "CONTAINS"
    INTERACTS_WITH = "INTERACTS_WITH"
    CONTRAINDICATED_WITH = "CONTRAINDICATED_WITH"
    GROWS_IN = "GROWS_IN"
    REQUIRES = "REQUIRES"
    HAS_VARIETY = "HAS_VARIETY"
    RESISTANT_TO = "RESISTANT_TO"
    SUSCEPTIBLE_TO = "SUSCEPTIBLE_TO"
    THRIVES_IN = "THRIVES_IN"
    AFFECTED_BY_WEATHER = "AFFECTED_BY_WEATHER"
    PLANTED_IN_SEASON = "PLANTED_IN_SEASON"
    LOCATED_IN = "LOCATED_IN"
    SOLD_AT = "SOLD_AT"
    COVERED_BY_SCHEME = "COVERED_BY_SCHEME"
    ALSO_KNOWN_AS = "ALSO_KNOWN_AS"
    PART_OF = "PART_OF"
    RELATED_TO = "RELATED_TO"
    SOURCE_OF = "SOURCE_OF"


class NodeSchema(BaseModel):
    node_type: NodeType
    required_properties: list[str] = Field(default_factory=list)
    optional_properties: list[str] = Field(default_factory=list)
    multilingual_fields: list[str] = Field(default_factory=list)
    safety_critical: bool = False
    requires_approval: bool = False

    class Config:
        frozen = True


class RelationshipSchema(BaseModel):
    relationship_type: RelationshipType
    source_types: list[NodeType]
    target_types: list[NodeType]
    required_properties: list[str] = Field(default_factory=list)
    optional_properties: list[str] = Field(default_factory=list)
    safety_critical: bool = False
    requires_approval: bool = False
    temporal_validity: bool = False

    class Config:
        frozen = True


class Ontology(BaseModel):
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    node_schemas: dict[NodeType, NodeSchema] = Field(default_factory=dict)
    relationship_schemas: dict[RelationshipType, RelationshipSchema] = Field(default_factory=dict)
    english_aliases: dict[str, list[str]] = Field(default_factory=dict)
    hindi_aliases: dict[str, list[str]] = Field(default_factory=dict)
    marathi_aliases: dict[str, list[str]] = Field(default_factory=dict)
    high_risk_nodes: set[NodeType] = Field(default_factory=set)
    high_risk_relationships: set[RelationshipType] = Field(default_factory=set)

    @classmethod
    def create_default(cls) -> "Ontology":
        ontology = cls()
        ontology.node_schemas = {
            NodeType.CROP: NodeSchema(node_type=NodeType.CROP, required_properties=["name", "scientific_name"], multilingual_fields=["name", "description"]),
            NodeType.DISEASE: NodeSchema(node_type=NodeType.DISEASE, required_properties=["name", "pathogen_type"], multilingual_fields=["name", "description"]),
            NodeType.PEST: NodeSchema(node_type=NodeType.PEST, required_properties=["name", "pest_type"], multilingual_fields=["name", "description"]),
            NodeType.CHEMICAL: NodeSchema(node_type=NodeType.CHEMICAL, required_properties=["name", "active_ingredient", "registration_number"], safety_critical=True, requires_approval=True),
            NodeType.FERTILIZER: NodeSchema(node_type=NodeType.FERTILIZER, required_properties=["name", "npk_ratio"]),
            NodeType.SYMPTOM: NodeSchema(node_type=NodeType.SYMPTOM, required_properties=["name", "description"], multilingual_fields=["name", "description"]),
            NodeType.TREATMENT: NodeSchema(node_type=NodeType.TREATMENT, required_properties=["name", "treatment_type"], safety_critical=True, requires_approval=True),
            NodeType.DOSAGE: NodeSchema(node_type=NodeType.DOSAGE, required_properties=["amount", "unit", "application_method"], safety_critical=True, requires_approval=True),
            NodeType.SOIL_TYPE: NodeSchema(node_type=NodeType.SOIL_TYPE, required_properties=["name", "soil_class"]),
            NodeType.WEATHER_CONDITION: NodeSchema(node_type=NodeType.WEATHER_CONDITION, required_properties=["name", "condition_type"]),
            NodeType.SEASON: NodeSchema(node_type=NodeType.SEASON, required_properties=["name", "start_month", "end_month"]),
            NodeType.GOVERNMENT_SCHEME: NodeSchema(node_type=NodeType.GOVERNMENT_SCHEME, required_properties=["name", "scheme_id", "ministry"], requires_approval=True),
            NodeType.MARKET: NodeSchema(node_type=NodeType.MARKET, required_properties=["name", "market_type"]),
            NodeType.LOCATION: NodeSchema(node_type=NodeType.LOCATION, required_properties=["name", "location_type"]),
            NodeType.VARIETY: NodeSchema(node_type=NodeType.VARIETY, required_properties=["name", "crop_id"]),
            NodeType.PRACTICE: NodeSchema(node_type=NodeType.PRACTICE, required_properties=["name", "practice_type"], multilingual_fields=["name", "description"]),
        }
        ontology.relationship_schemas = {
            RelationshipType.AFFECTED_BY: RelationshipSchema(relationship_type=RelationshipType.AFFECTED_BY, source_types=[NodeType.CROP, NodeType.VARIETY], target_types=[NodeType.DISEASE, NodeType.PEST], required_properties=["severity", "frequency"]),
            RelationshipType.HAS_SYMPTOM: RelationshipSchema(relationship_type=RelationshipType.HAS_SYMPTOM, source_types=[NodeType.DISEASE, NodeType.PEST], target_types=[NodeType.SYMPTOM], required_properties=["stage"]),
            RelationshipType.TREATED_BY: RelationshipSchema(relationship_type=RelationshipType.TREATED_BY, source_types=[NodeType.DISEASE, NodeType.PEST], target_types=[NodeType.TREATMENT, NodeType.CHEMICAL], required_properties=["efficacy_score"], safety_critical=True, requires_approval=True, temporal_validity=True),
            RelationshipType.HAS_DOSAGE: RelationshipSchema(relationship_type=RelationshipType.HAS_DOSAGE, source_types=[NodeType.CHEMICAL, NodeType.FERTILIZER], target_types=[NodeType.DOSAGE], required_properties=["crop_id", "growth_stage"], safety_critical=True, requires_approval=True),
            RelationshipType.GROWS_IN: RelationshipSchema(relationship_type=RelationshipType.GROWS_IN, source_types=[NodeType.CROP], target_types=[NodeType.SOIL_TYPE], required_properties=["suitability_score"]),
            RelationshipType.REQUIRES: RelationshipSchema(relationship_type=RelationshipType.REQUIRES, source_types=[NodeType.CROP], target_types=[NodeType.PRACTICE, NodeType.FERTILIZER], required_properties=["timing"]),
            RelationshipType.INTERACTS_WITH: RelationshipSchema(relationship_type=RelationshipType.INTERACTS_WITH, source_types=[NodeType.CHEMICAL], target_types=[NodeType.CHEMICAL], required_properties=["interaction_type"], safety_critical=True, requires_approval=True),
            RelationshipType.CONTRAINDICATED_WITH: RelationshipSchema(relationship_type=RelationshipType.CONTRAINDICATED_WITH, source_types=[NodeType.CHEMICAL], target_types=[NodeType.CHEMICAL, NodeType.CROP], required_properties=["reason"], safety_critical=True, requires_approval=True),
            RelationshipType.ALSO_KNOWN_AS: RelationshipSchema(relationship_type=RelationshipType.ALSO_KNOWN_AS, source_types=[NodeType.CROP, NodeType.DISEASE, NodeType.PEST, NodeType.CHEMICAL], target_types=[NodeType.ALIAS_EN, NodeType.ALIAS_HI, NodeType.ALIAS_MR], required_properties=["language"]),
        }
        ontology.high_risk_nodes = {NodeType.CHEMICAL, NodeType.DOSAGE, NodeType.TREATMENT}
        ontology.high_risk_relationships = {RelationshipType.TREATED_BY, RelationshipType.HAS_DOSAGE, RelationshipType.INTERACTS_WITH, RelationshipType.CONTRAINDICATED_WITH}
        return ontology

    def is_high_risk_node(self, node_type: NodeType) -> bool:
        return node_type in self.high_risk_nodes

    def is_high_risk_relationship(self, rel_type: RelationshipType) -> bool:
        return rel_type in self.high_risk_relationships

    def requires_approval(self, node_type: NodeType) -> bool:
        schema = self.node_schemas.get(node_type)
        return schema.requires_approval if schema else False

    def get_multilingual_fields(self, node_type: NodeType) -> list[str]:
        schema = self.node_schemas.get(node_type)
        return schema.multilingual_fields if schema else []


class GraphNode(BaseModel):
    node_id: str
    node_type: NodeType
    properties: dict[str, str | int | float | bool]
    source_id: str
    checksum: str
    confidence: float = 1.0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    requires_approval: bool = False
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def mark_approved(self, approver: str) -> None:
        object.__setattr__(self, "approved", True)
        object.__setattr__(self, "approved_by", approver)
        object.__setattr__(self, "approved_at", datetime.utcnow())

    class Config:
        arbitrary_types_allowed = True


class GraphRelationship(BaseModel):
    relationship_id: str
    relationship_type: RelationshipType
    source_node_id: str
    target_node_id: str
    properties: dict[str, str | int | float | bool]
    source_id: str
    checksum: str
    confidence: float = 1.0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    requires_approval: bool = False
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def mark_approved(self, approver: str) -> None:
        object.__setattr__(self, "approved", True)
        object.__setattr__(self, "approved_by", approver)
        object.__setattr__(self, "approved_at", datetime.utcnow())

    class Config:
        arbitrary_types_allowed = True


class GraphPath(BaseModel):
    path_id: str
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
    confidence: float
    citations: list[str]

    @property
    def is_complete(self) -> bool:
        all_approved = all((n.approved or not n.requires_approval) for n in self.nodes) and all((r.approved or not r.requires_approval) for r in self.relationships)
        return all_approved
