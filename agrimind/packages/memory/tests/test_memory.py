"""Tests for memory package - Graph, Vector, and Retrieval."""

import pytest
from datetime import datetime
from memory.graph.ontology import (
    NodeType, RelationshipType, Ontology, 
    GraphNode, GraphRelationship, GraphPath
)
from memory.vector.embeddings import (
    EmbeddingModel, EmbeddingConfig, VectorDocument, 
    EmbeddingResult, SemanticCacheEntry
)
from memory.retrieval.service import (
    RetrievalMode, ChunkWithCitation, GraphPathResult,
    RetrievalRequest, RetrievalResult, RetrievalConfig, RetrievalTrace
)


class TestOntology:
    """Test knowledge graph ontology."""
    
    def test_create_default_ontology(self):
        """Test creating default ontology."""
        ontology = Ontology.create_default()
        
        assert ontology.version == "1.0.0"
        assert len(ontology.node_schemas) > 0
        assert len(ontology.relationship_schemas) > 0
        
        # Check high-risk nodes
        assert NodeType.CHEMICAL in ontology.high_risk_nodes
        assert NodeType.DOSAGE in ontology.high_risk_nodes
        assert NodeType.TREATMENT in ontology.high_risk_nodes
    
    def test_high_risk_detection(self):
        """Test high-risk node and relationship detection."""
        ontology = Ontology.create_default()
        
        assert ontology.is_high_risk_node(NodeType.CHEMICAL) is True
        assert ontology.is_high_risk_node(NodeType.CROP) is False
        assert ontology.is_high_risk_relationship(RelationshipType.HAS_DOSAGE) is True
        assert ontology.is_high_risk_relationship(RelationshipType.AFFECTED_BY) is False
    
    def test_approval_requirements(self):
        """Test approval requirements for nodes."""
        ontology = Ontology.create_default()
        
        assert ontology.requires_approval(NodeType.CHEMICAL) is True
        assert ontology.requires_approval(NodeType.DOSAGE) is True
        assert ontology.requires_approval(NodeType.TREATMENT) is True
        assert ontology.requires_approval(NodeType.CROP) is False
    
    def test_multilingual_fields(self):
        """Test multilingual field retrieval."""
        ontology = Ontology.create_default()
        
        crop_fields = ontology.get_multilingual_fields(NodeType.CROP)
        assert "name" in crop_fields
        assert "description" in crop_fields
        
        chemical_fields = ontology.get_multilingual_fields(NodeType.CHEMICAL)
        assert "name" in chemical_fields
    
    def test_graph_node_creation(self):
        """Test creating graph node."""
        node = GraphNode(
            node_id="crop-001",
            node_type=NodeType.CROP,
            properties={"name": "Cotton", "scientific_name": "Gossypium"},
            source_id="src-001",
            checksum="sha256:abc123",
        )
        
        assert node.approved is False
        assert node.requires_approval is False
    
    def test_graph_node_approval(self):
        """Test approving graph node."""
        node = GraphNode(
            node_id="chemical-001",
            node_type=NodeType.CHEMICAL,
            properties={"name": "Glyphosate", "active_ingredient": "Glyphosate"},
            source_id="src-001",
            checksum="sha256:xyz789",
            requires_approval=True,
        )
        
        assert node.approved is False
        node.mark_approved("agronomist-1")
        assert node.approved is True
        assert node.approved_by == "agronomist-1"
    
    def test_graph_path_completeness(self):
        """Test graph path completeness check."""
        crop_node = GraphNode(
            node_id="crop-001",
            node_type=NodeType.CROP,
            properties={"name": "Cotton"},
            source_id="src-001",
            checksum="sha256:abc",
        )
        
        disease_node = GraphNode(
            node_id="disease-001",
            node_type=NodeType.DISEASE,
            properties={"name": "Bollworm"},
            source_id="src-001",
            checksum="sha256:def",
        )
        
        relationship = GraphRelationship(
            relationship_id="rel-001",
            relationship_type=RelationshipType.AFFECTED_BY,
            source_node_id="crop-001",
            target_node_id="disease-001",
            properties={"severity": "high"},
            source_id="src-001",
            checksum="sha256:ghi",
        )
        
        path = GraphPath(
            path_id="path-001",
            nodes=[crop_node, disease_node],
            relationships=[relationship],
            confidence=0.95,
            citations=["src-001"],
        )
        
        assert path.is_complete is True


class TestEmbeddings:
    """Test embedding service contracts."""
    
    def test_embedding_config_defaults(self):
        """Test embedding configuration defaults."""
        config = EmbeddingConfig()
        
        assert config.model == EmbeddingModel.BGE_MULTILINGUAL
        assert config.dimension == 1024
        assert config.max_length == 512
        assert config.normalize is True
        assert config.cache_enabled is True
    
    def test_vector_document_creation(self):
        """Test creating vector document."""
        content = "Cotton crop requires adequate irrigation"
        source_id = "src-agri-001"
        
        doc = VectorDocument(
            doc_id="doc-001",
            content=content,
            embedding=[0.1] * 1024,
            source_id=source_id,
            lang="en",
            checksum=VectorDocument.compute_checksum(content, source_id),
        )
        
        assert doc.lang == "en"
        assert len(doc.embedding) == 1024
    
    def test_checksum_computation(self):
        """Test checksum computation consistency."""
        content = "Test content"
        source_id = "src-001"
        
        checksum1 = VectorDocument.compute_checksum(content, source_id)
        checksum2 = VectorDocument.compute_checksum(content, source_id)
        
        assert checksum1 == checksum2
        
        checksum3 = VectorDocument.compute_checksum("Different content", source_id)
        assert checksum3 != checksum1
    
    def test_semantic_cache_entry(self):
        """Test semantic cache entry."""
        import time
        
        entry = SemanticCacheEntry(
            query_hash="hash-001",
            query_text="कपाशीवर बोंडअळी आली आहे",
            cached_results=["doc-001", "doc-002"],
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        
        assert entry.is_expired is False
        assert entry.hit_count == 0
        
        entry.record_hit()
        assert entry.hit_count == 1


class TestRetrievalService:
    """Test retrieval service contracts."""
    
    def test_retrieval_request_defaults(self):
        """Test retrieval request default values."""
        request = RetrievalRequest(
            query="What is the treatment for cotton bollworm?",
            lang="en",
        )
        
        assert request.mode == RetrievalMode.AUTO
        assert request.top_k == 8
        assert request.require_citations is True
        assert request.min_confidence == 0.7
    
    def test_chunk_with_citation(self):
        """Test chunk with citation creation."""
        chunk = ChunkWithCitation(
            chunk_id="chunk-001",
            content="IPM practices are recommended for bollworm control",
            score=0.92,
            source_id="src-icar-001",
            source_type="government_publication",
            url_or_path="https://icar.org.in/cotton-ipm",
            checksum="sha256:abc123",
            lang="en",
        )
        
        assert chunk.score == 0.92
        assert chunk.lang == "en"
        assert chunk.source_id == "src-icar-001"
    
    def test_retrieval_result_aggregation(self):
        """Test retrieval result aggregation."""
        chunks = [
            ChunkWithCitation(
                chunk_id=f"chunk-{i}",
                content=f"Content {i}",
                score=0.9,
                source_id="src-001",
                source_type="document",
                url_or_path="/path",
                checksum="sha256:abc",
                lang="en",
            )
            for i in range(3)
        ]
        
        graph_paths = [
            GraphPathResult(
                path_id="path-001",
                start_node="cotton",
                end_node="bollworm_treatment",
                nodes=[],
                relationships=[],
                confidence=0.95,
                citations=["src-001"],
            )
        ]
        
        result = RetrievalResult(
            request_id="req-001",
            query="Cotton bollworm treatment",
            chunks=chunks,
            graph_paths=graph_paths,
            confidence=0.93,
        )
        
        assert result.result_count == 4
        assert result.has_citations is True
    
    def test_high_risk_content_detection(self):
        """Test high-risk content detection in results."""
        safe_chunk = ChunkWithCitation(
            chunk_id="chunk-safe",
            content="Cotton grows well in black soil",
            score=0.9,
            source_id="src-001",
            source_type="document",
            url_or_path="/path",
            checksum="sha256:abc",
            lang="en",
            metadata={"safety_critical": False},
        )
        
        safe_result = RetrievalResult(
            request_id="req-safe",
            query="Cotton soil type",
            chunks=[safe_chunk],
            confidence=0.9,
        )
        
        assert safe_result.has_high_risk_content() is False
        
        risky_chunk = ChunkWithCitation(
            chunk_id="chunk-risky",
            content="Apply 500ml per hectare",
            score=0.88,
            source_id="src-chem-001",
            source_type="chemical_guide",
            url_or_path="/chemical-guide",
            checksum="sha256:xyz",
            lang="en",
            metadata={"safety_critical": True},
        )
        
        risky_result = RetrievalResult(
            request_id="req-risky",
            query="Pesticide dosage",
            chunks=[risky_chunk],
            confidence=0.88,
        )
        
        assert risky_result.has_high_risk_content() is True
        assert risky_result.requires_approval is True
    
    def test_retrieval_trace(self):
        """Test retrieval trace for observability."""
        trace = RetrievalTrace(
            mode=RetrievalMode.HYBRID,
            query="कपाशीवर बोंडअळी उपचार",
            graph_results_count=2,
            vector_results_count=5,
            reranking_applied=True,
            cache_hit=False,
            total_latency_ms=245.0,
        )
        
        assert trace.trace_id is not None
        assert trace.reranking_applied is True
        assert trace.cache_hit is False
    
    def test_retrieval_config_frozen(self):
        """Test retrieval config is frozen."""
        config = RetrievalConfig()
        
        assert config.default_mode == RetrievalMode.HYBRID
        assert config.p95_latency_target_ms == 300.0
        
        with pytest.raises(Exception):
            config.default_top_k = 20


class TestIntegration:
    """Integration tests for memory components."""
    
    def test_end_to_end_retrieval_flow(self):
        """Test complete retrieval flow from request to result."""
        request = RetrievalRequest(
            query="कापूस पिकावरील बोंडअळी नियंत्रण",
            lang="mr",
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )
        
        chunks = [
            ChunkWithCitation(
                chunk_id="chunk-mr-001",
                content="बोंडअळी नियंत्रणासाठी एकात्मिक कीटक व्यवस्थापन (IPM) पद्धती वापराव्यात",
                score=0.94,
                source_id="src-maha-agri-001",
                source_type="government_advisory",
                url_or_path="https://mahagri.gov.in/cotton-ipm",
                checksum="sha256:mr123",
                lang="mr",
                metadata={"safety_critical": False},
            )
        ]
        
        graph_path = GraphPathResult(
            path_id="path-cotton-bollworm",
            start_node="कापूस",
            end_node="बोंडअळी_उपचार",
            nodes=[
                {"id": "crop-cotton", "type": "Crop"},
                {"id": "pest-bollworm", "type": "Pest"},
                {"id": "treatment-ipm", "type": "Treatment"},
            ],
            relationships=[
                {"type": "AFFECTED_BY"},
                {"type": "TREATED_BY"},
            ],
            confidence=0.96,
            citations=["src-maha-agri-001"],
            is_approved=True,
        )
        
        result = RetrievalResult(
            request_id=request.request_id,
            query=request.query,
            chunks=chunks,
            graph_paths=[graph_path],
            confidence=0.95,
            has_citations=True,
        )
        
        assert result.request_id == request.request_id
        assert result.result_count == 2
        assert result.confidence >= request.min_confidence
        assert result.has_citations is True
        assert result.has_high_risk_content() is False
