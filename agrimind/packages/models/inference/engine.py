"""Inference Engine for cloud and edge model serving."""
from typing import AsyncIterator, Optional
import time
from .contracts import InferenceRequest, InferenceResponse


class InferenceEngine:
    """Abstract inference engine supporting cloud and edge deployment."""
    
    def __init__(self, model_id: str, endpoint: str, is_edge: bool = False):
        self.model_id = model_id
        self.endpoint = endpoint
        self.is_edge = is_edge
    
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """Generate completion for a single request."""
        start_time = time.time()
        
        # Validate model match
        if request.model_id != self.model_id:
            raise ValueError(f"Model mismatch: expected {self.model_id}, got {request.model_id}")
        
        # Simulate inference (in real implementation, calls vLLM/SGLang/ONNX)
        completion = f"[Simulated response for: {request.prompt[:50]}...]"
        latency_ms = (time.time() - start_time) * 1000
        
        return InferenceResponse(
            request_id=request.request_id,
            model_id=self.model_id,
            completion=completion,
            finish_reason="stop",
            usage={
                "prompt_tokens": len(request.prompt.split()),
                "completion_tokens": len(completion.split()),
                "total_tokens": len(request.prompt.split()) + len(completion.split())
            },
            latency_ms=latency_ms
        )
    
    async def generate_stream(
        self, request: InferenceRequest
    ) -> AsyncIterator[str]:
        """Stream completion tokens."""
        if not request.stream:
            raise ValueError("Stream must be enabled for streaming generation")
        
        # Simulate streaming (in real implementation, uses SSE)
        tokens = ["This", " is", " a", " simulated", " stream", " response", "."]
        for token in tokens:
            yield token
    
    def health_check(self) -> bool:
        """Check if inference engine is healthy."""
        # In real implementation, checks endpoint connectivity
        return True
