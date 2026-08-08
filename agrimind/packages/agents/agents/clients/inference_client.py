"""Inference-service HTTP client with local simulated fallback."""

from __future__ import annotations

from typing import Any

import httpx


class InferenceClient:
    """
    Prefer inference-service /v1/generate over HTTP.
    Local fallback only when allow_local_fallback=True.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8004",
        *,
        timeout: float = 5.0,
        allow_local_fallback: bool = True,
        default_model: str = "agrimind-7b-sim-v0.1.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.allow_local_fallback = allow_local_fallback
        self.default_model = default_model
        self._client = client

    async def generate(
        self,
        prompt: str,
        *,
        model_id: str | None = None,
        intent: str | None = None,
        lang: str | None = None,
        evidence: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "model_id": model_id or self.default_model,
            "intent": intent,
            "lang": lang,
            "evidence": evidence,
            "max_tokens": 512,
            "temperature": 0.2,
        }
        hdrs = headers or {}
        try:
            if self._client is not None:
                resp = await self._client.post(
                    f"{self.base_url}/v1/generate",
                    json=payload,
                    headers=hdrs,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/generate",
                        json=payload,
                        headers=hdrs,
                    )
            resp.raise_for_status()
            data = resp.json()
            data["_backend"] = "http"
            data["_inference_url"] = self.base_url
            return data
        except Exception as exc:
            if not self.allow_local_fallback:
                raise RuntimeError(f"inference-service unreachable: {exc}") from exc
            local = self.generate_local(
                prompt,
                model_id=model_id or self.default_model,
                intent=intent,
                lang=lang,
                evidence=evidence,
            )
            local["_backend"] = "local_fallback"
            local["_fallback_reason"] = str(exc)
            return local

    def generate_local(
        self,
        prompt: str,
        *,
        model_id: str,
        intent: str | None = None,
        lang: str | None = None,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        completion = build_grounded_completion(
            prompt=prompt,
            model_id=model_id,
            intent=intent or "general_advisory",
            lang=lang or "en",
            evidence=evidence or "",
        )
        return {
            "request_id": "local",
            "model_id": model_id,
            "completion": completion,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(completion.split()),
                "total_tokens": len(prompt.split()) + len(completion.split()),
            },
            "latency_ms": 0.0,
            "simulated": True,
        }


def build_grounded_completion(
    *,
    prompt: str,
    model_id: str,
    intent: str,
    lang: str,
    evidence: str,
) -> str:
    """Shared grounded draft builder (used by inference-service + local fallback)."""
    if intent in ("disease_diagnosis", "chemical_dosage"):
        advice = (
            "Recommendation: use integrated pest management (monitoring, traps, "
            "approved products only). Consult local KVK before chemical use."
        )
    elif intent == "govt_scheme":
        advice = "Recommendation: verify scheme eligibility with local agriculture office."
    elif intent == "weather_advisory":
        advice = "Recommendation: adjust field operations for the forecast; avoid spray before rain."
    elif intent == "market_price":
        advice = "Recommendation: compare nearby mandi prices before selling."
    else:
        advice = "Recommendation: follow good agronomic practices for soil and crop health."

    evidence_bit = evidence.strip() or "none"
    return (
        f"[sim-model:{model_id} intent={intent} lang={lang}] "
        f"Based on retrieved evidence: {evidence_bit}. {advice}"
    )
