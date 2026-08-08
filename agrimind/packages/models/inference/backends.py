"""Inference backends: grounded sim + OpenAI-compatible (vLLM/SGLang)."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Protocol

from inference.contracts import InferenceRequest, InferenceResponse


class InferenceBackend(Protocol):
    name: str
    simulated: bool

    async def generate(self, request: InferenceRequest, **context: Any) -> InferenceResponse: ...

    async def generate_stream(self, request: InferenceRequest, **context: Any) -> AsyncIterator[str]: ...

    def health_check(self) -> bool: ...


class GroundedSimBackend:
    """
    Offline-safe grounded completion (not a real LLM).
    Used when no vLLM/SGLang endpoint is configured.
    """

    name = "grounded_sim"
    simulated = True

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    async def generate(self, request: InferenceRequest, **context: Any) -> InferenceResponse:
        start = time.time()
        intent = str(context.get("intent") or "general_advisory")
        lang = str(context.get("lang") or "en")
        evidence = str(context.get("evidence") or "")
        try:
            from agents.clients.inference_client import build_grounded_completion

            completion = build_grounded_completion(
                prompt=request.prompt,
                model_id=request.model_id or self.model_id,
                intent=intent,
                lang=lang,
                evidence=evidence,
            )
        except Exception:
            completion = (
                f"[sim-model:{request.model_id}] intent={intent} lang={lang} "
                f"evidence={evidence[:200] or 'none'}. Prefer IPM and KVK referral."
            )
        latency = (time.time() - start) * 1000
        return InferenceResponse(
            request_id=request.request_id,
            model_id=request.model_id,
            completion=completion,
            finish_reason="stop",
            usage={
                "prompt_tokens": max(1, len(request.prompt.split())),
                "completion_tokens": max(1, len(completion.split())),
                "total_tokens": max(1, len(request.prompt.split()) + len(completion.split())),
            },
            latency_ms=latency,
            warnings=["simulated_backend"],
        )

    async def generate_stream(self, request: InferenceRequest, **context: Any) -> AsyncIterator[str]:
        resp = await self.generate(request, **context)
        for tok in resp.completion.split(" "):
            yield tok + " "

    def health_check(self) -> bool:
        return True


class OpenAICompatBackend:
    """
    OpenAI-compatible chat/completions client for vLLM, SGLang, or any
    OpenAI API-compatible server (D1 remote path).
    """

    name = "openai_compat"
    simulated = False

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "EMPTY",
        default_model: str = "agrimind-7b",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    def _url(self, path: str) -> str:
        # accept base ending with /v1 or bare host
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/v1{path}"

    async def generate(self, request: InferenceRequest, **context: Any) -> InferenceResponse:
        import httpx

        start = time.time()
        model = request.model_id or self.default_model
        # Prefer chat.completions for SGLang/vLLM defaults
        system = (
            "You are AGRIMIND, an agricultural advisory assistant. "
            "Use only provided evidence. Do not invent chemical dosages. "
            "Prefer IPM and refer to KVK when uncertain."
        )
        evidence = context.get("evidence") or ""
        user_content = request.prompt
        if evidence:
            user_content = f"Evidence:\n{evidence}\n\n{request.prompt}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._url("/chat/completions"),
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        completion = message.get("content") or choice.get("text") or ""
        usage = data.get("usage") or {}
        latency = (time.time() - start) * 1000
        return InferenceResponse(
            request_id=request.request_id,
            model_id=model,
            completion=completion,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or len(request.prompt.split())),
                "completion_tokens": int(
                    usage.get("completion_tokens") or max(1, len(completion.split()))
                ),
                "total_tokens": int(
                    usage.get("total_tokens")
                    or (len(request.prompt.split()) + len(completion.split()))
                ),
            },
            latency_ms=latency,
            warnings=None,
        )

    async def generate_stream(self, request: InferenceRequest, **context: Any) -> AsyncIterator[str]:
        # Minimal non-stream fallback: yield full completion as one chunk
        resp = await self.generate(request, **context)
        yield resp.completion

    def health_check(self) -> bool:
        try:
            import httpx

            r = httpx.get(self._url("/models"), timeout=3.0, headers={"Authorization": f"Bearer {self.api_key}"})
            return r.status_code < 500
        except Exception:
            return False


def build_backend(
    *,
    mode: str = "auto",
    model_id: str = "agrimind-7b-sim-v0.1.0",
    vllm_base_url: str | None = None,
    vllm_api_key: str = "EMPTY",
) -> InferenceBackend:
    """
    mode:
      - sim: always GroundedSimBackend
      - remote: OpenAICompatBackend (fail if no URL)
      - auto: remote if VLLM_BASE_URL set, else sim
    """
    m = (mode or "auto").lower()
    if m == "sim":
        return GroundedSimBackend(model_id)
    if m == "remote":
        if not vllm_base_url:
            raise ValueError("INFERENCE_MODE=remote requires VLLM_BASE_URL / INFERENCE_REMOTE_URL")
        return OpenAICompatBackend(vllm_base_url, api_key=vllm_api_key, default_model=model_id)
    # auto
    if vllm_base_url:
        return OpenAICompatBackend(vllm_base_url, api_key=vllm_api_key, default_model=model_id)
    return GroundedSimBackend(model_id)
