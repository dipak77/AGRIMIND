"""Inference engine with registry gate + pluggable backends (Phase D)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from inference.backends import InferenceBackend, GroundedSimBackend, build_backend
from inference.contracts import InferenceRequest, InferenceResponse


class InferenceEngine:
    """Cloud/edge serving façade with optional model-registry serve gate."""

    def __init__(
        self,
        model_id: str,
        *,
        backend: InferenceBackend | None = None,
        registry: Any | None = None,
        require_registry: bool = False,
        is_edge: bool = False,
        endpoint: str = "",
    ) -> None:
        self.model_id = model_id
        self.is_edge = is_edge
        self.endpoint = endpoint
        self.registry = registry
        self.require_registry = require_registry
        self.backend = backend or GroundedSimBackend(model_id)

    @classmethod
    def from_settings(
        cls,
        *,
        model_id: str,
        mode: str = "auto",
        vllm_base_url: str | None = None,
        vllm_api_key: str = "EMPTY",
        registry: Any | None = None,
        require_registry: bool = False,
        is_edge: bool = False,
    ) -> "InferenceEngine":
        backend = build_backend(
            mode=mode,
            model_id=model_id,
            vllm_base_url=vllm_base_url,
            vllm_api_key=vllm_api_key,
        )
        return cls(
            model_id=model_id,
            backend=backend,
            registry=registry,
            require_registry=require_registry,
            is_edge=is_edge,
            endpoint=vllm_base_url or "",
        )

    def _gate_model(self, model_id: str) -> None:
        """Fail loud if registry present and model is not servable."""
        if self.registry is None:
            if self.require_registry:
                raise RuntimeError("Model registry required but not configured")
            return
        try:
            from registry.gates import assert_model_servable

            assert_model_servable(self.registry, model_id)
        except ImportError:
            # gates module always expected in package
            raise

    async def generate(self, request: InferenceRequest, **context: Any) -> InferenceResponse:
        mid = request.model_id or self.model_id
        if request.model_id and request.model_id != self.model_id:
            # allow multi-model engines only if ids match requested backend default or registry
            pass
        self._gate_model(mid)
        # normalize request model_id
        req = request
        if not req.model_id:
            req = request.model_copy(update={"model_id": mid})
        resp = await self.backend.generate(req, **context)
        # tag simulated flag via warnings already
        return resp

    async def generate_stream(
        self, request: InferenceRequest, **context: Any
    ) -> AsyncIterator[str]:
        if not request.stream:
            raise ValueError("Stream must be enabled for streaming generation")
        mid = request.model_id or self.model_id
        self._gate_model(mid)
        async for tok in self.backend.generate_stream(request, **context):
            yield tok

    def health_check(self) -> bool:
        return self.backend.health_check()

    @property
    def simulated(self) -> bool:
        return bool(getattr(self.backend, "simulated", True))

    @property
    def backend_name(self) -> str:
        return str(getattr(self.backend, "name", "unknown"))
