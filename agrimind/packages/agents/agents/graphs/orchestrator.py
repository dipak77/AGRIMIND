"""
Bounded agent pipeline (plan Phase 6).

Flow:
  intent -> retrieval (memory-service HTTP) -> tools
        -> generate (inference-service HTTP) -> safety -> finalize

HTTP is preferred; local fallback only when allow_local_fallback=True.
"""

from __future__ import annotations

import uuid
from typing import Any

from agents.clients.inference_client import InferenceClient, build_grounded_completion
from agents.clients.memory_client import MemoryClient
from agents.graphs.state import AgentState
from agents.tools.market import MarketTool
from agents.tools.weather import WeatherTool
from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.contracts import Citation, Language, Query, Response, SafetyLevel
from agrimind_kernel.safety_engine import SafetyEngine

_safety = SafetyEngine()
_weather = WeatherTool()
_market = MarketTool()


def _clients(
    *,
    memory_url: str | None = None,
    inference_url: str | None = None,
    allow_local_fallback: bool | None = None,
    http_client: Any = None,
) -> tuple[MemoryClient, InferenceClient]:
    settings = get_settings()
    env = settings.env.lower()
    if allow_local_fallback is None:
        allow_local_fallback = env in ("local", "dev", "test")
    mem = MemoryClient(
        base_url=memory_url or settings.memory_service_url,
        allow_local_fallback=allow_local_fallback,
        client=http_client,
    )
    inf = InferenceClient(
        base_url=inference_url or settings.inference_service_url,
        allow_local_fallback=allow_local_fallback,
        default_model=settings.default_cloud_model,
        client=http_client,
    )
    return mem, inf


def intent_classifier_node(state: AgentState) -> AgentState:
    q = state["query"].text.lower()
    if any(k in q for k in ("disease", "pest", "bollworm", "रोग", "कीड", "अळी")):
        state["intent"] = "disease_diagnosis"
    elif any(k in q for k in ("price", "market", "भाव", "बाजार")):
        state["intent"] = "market_price"
    elif any(k in q for k in ("weather", "rain", "हवामान", "पाऊस")):
        state["intent"] = "weather_advisory"
    elif any(k in q for k in ("scheme", "subsidy", "योजना", "अनुदान")):
        state["intent"] = "govt_scheme"
    elif any(k in q for k in ("dosage", "spray", "ml", "pesticide", "फवारणी")):
        state["intent"] = "chemical_dosage"
    else:
        state["intent"] = "general_advisory"
    return state


async def retrieval_node_async(
    state: AgentState,
    memory: MemoryClient,
    *,
    headers: dict[str, str] | None = None,
) -> AgentState:
    query = state["query"]
    lang = query.lang.value if isinstance(query.lang, Language) else str(query.lang)
    result = await memory.retrieve(
        query.text,
        lang=lang,
        mode="hybrid",
        top_k=5,
        headers=headers,
    )
    citations = MemoryClient.parse_citations(result)
    # drop Nones
    state["citations"] = [c for c in citations if isinstance(c, Citation)]
    state["confidence"] = float(result.get("confidence") or 0.5)
    state["retrieval_results"] = result
    # stash backend markers without colliding with tools
    state.setdefault("tool_outputs", {})
    # use a side channel on state via retrieval_results already
    return state


async def tools_node(state: AgentState) -> AgentState:
    tools: dict[str, Any] = dict(state.get("tool_outputs") or {})
    intent = state.get("intent", "")
    if intent == "weather_advisory":
        district = "local"
        loc = state["query"].location
        if loc and loc.district:
            district = loc.district
        tools["weather"] = await _weather.get(district)
    if intent == "market_price":
        tools["market"] = await _market.get_price("cotton")
    state["tool_outputs"] = tools
    return state


def _build_prompt(state: AgentState) -> tuple[str, str]:
    citations = state.get("citations") or []
    evidence = "; ".join(
        (c.excerpt or c.span or c.title or c.source_id) for c in citations[:3]
    )
    tools = state.get("tool_outputs") or {}
    tool_bits = []
    if "weather" in tools:
        tool_bits.append(f"Weather: {tools['weather'].get('forecast')}")
    if "market" in tools:
        tool_bits.append(
            f"Market: {tools['market'].get('crop')} @ {tools['market'].get('price')} "
            f"({tools['market'].get('source')})"
        )
    tool_txt = " ".join(tool_bits)
    lang = state["query"].lang
    lang_s = lang.value if isinstance(lang, Language) else str(lang)
    intent = state.get("intent", "general_advisory")
    prompt = (
        f"Farmer query ({lang_s}): {state['query'].text}\n"
        f"Intent: {intent}\n"
        f"Evidence: {evidence or 'none'}\n"
        f"Tools: {tool_txt or 'none'}\n"
        "Write a safe agricultural advisory grounded only in evidence. "
        "Do not invent chemical dosages. Prefer IPM and KVK referral when uncertain."
    )
    return prompt, evidence


async def generator_node_async(
    state: AgentState,
    inference: InferenceClient,
    *,
    headers: dict[str, str] | None = None,
) -> AgentState:
    prompt, evidence = _build_prompt(state)
    lang = state["query"].lang
    lang_s = lang.value if isinstance(lang, Language) else str(lang)
    intent = state.get("intent", "general_advisory")

    result = await inference.generate(
        prompt,
        intent=intent,
        lang=lang_s,
        evidence=evidence,
        headers=headers,
    )
    draft = result.get("completion") or build_grounded_completion(
        prompt=prompt,
        model_id=result.get("model_id") or "unknown",
        intent=intent,
        lang=lang_s,
        evidence=evidence,
    )
    state["draft_answer"] = draft
    state["model_version"] = result.get("model_id") or "agrimind-7b-sim-v0.1.0"

    base = float(state.get("confidence") or 0.5)
    if intent == "chemical_dosage":
        cap = 0.90
    elif intent == "disease_diagnosis":
        cap = 0.88
    else:
        cap = 0.90
    # slightly lower confidence if either backend fell back
    retrieval = state.get("retrieval_results") or {}
    if retrieval.get("_backend") == "local_fallback" or result.get("_backend") == "local_fallback":
        cap = min(cap, 0.80)
        flags = list(state.get("safety_flags") or [])
        flags.append("service_local_fallback")
        state["safety_flags"] = flags
    state["confidence"] = min(base, cap)

    # record backends for observability
    state["retrieval_results"] = {
        **(retrieval if isinstance(retrieval, dict) else {"raw": retrieval}),
        "_generation_backend": result.get("_backend"),
        "_generation_fallback_reason": result.get("_fallback_reason"),
    }
    return state


def safety_node(state: AgentState) -> AgentState:
    query = state["query"]
    draft = state.get("draft_answer") or ""
    citations = state.get("citations") or []
    confidence = float(state.get("confidence") or 0.0)

    level_map = {
        "chemical_dosage": SafetyLevel.CHEMICAL_DOSAGE,
        "disease_diagnosis": SafetyLevel.PEST_TREATMENT,
        "govt_scheme": SafetyLevel.LEGAL_SCHEME,
        "weather_advisory": SafetyLevel.WEATHER_ACTION,
        "general_advisory": SafetyLevel.GENERAL,
        "market_price": SafetyLevel.GENERAL,
    }
    preset = level_map.get(state.get("intent", ""), SafetyLevel.GENERAL)

    result = _safety.evaluate(
        query=query,
        draft_response=draft,
        citations=citations,
        confidence=confidence,
        safety_level=preset,
    )
    existing = list(state.get("safety_flags") or [])
    state["safety_flags"] = existing + list(result.flags) + list(result.reasons)
    state["safety_level"] = result.safety_level.value

    if not result.passed:
        fb = _safety.create_safe_fallback_response(
            query,
            trace_id=state.get("trace_id"),
            reasons=result.flags or result.reasons,
        )
        state["final_answer"] = fb.answer
        state["confidence"] = fb.confidence
        state["fallback_used"] = True
        state["requires_review"] = True
        state["action"] = fb.action
        state["model_version"] = fb.model_version
        if not citations:
            state["citations"] = []
    else:
        state["final_answer"] = draft
        state["fallback_used"] = False
        state["requires_review"] = False
        state["action"] = "answer"
    return state


def _initial_state(query: Query, trace_id: str | None) -> AgentState:
    return {
        "query": query,
        "intent": "",
        "retrieval_results": None,
        "tool_outputs": {},
        "draft_answer": "",
        "safety_flags": [],
        "confidence": 0.0,
        "citations": [],
        "final_answer": "",
        "model_version": "agrimind-7b-sim-v0.1.0",
        "safety_level": SafetyLevel.GENERAL.value,
        "action": "answer",
        "fallback_used": False,
        "requires_review": False,
        "trace_id": trace_id or str(uuid.uuid4()),
    }


async def run_agent_async(
    query: Query,
    trace_id: str | None = None,
    *,
    memory_url: str | None = None,
    inference_url: str | None = None,
    allow_local_fallback: bool | None = None,
    http_client: Any = None,
    headers: dict[str, str] | None = None,
) -> AgentState:
    memory, inference = _clients(
        memory_url=memory_url,
        inference_url=inference_url,
        allow_local_fallback=allow_local_fallback,
        http_client=http_client,
    )
    hdrs = {"X-Request-ID": trace_id or str(uuid.uuid4()), **(headers or {})}
    state = _initial_state(query, trace_id)
    state = intent_classifier_node(state)
    state = await retrieval_node_async(state, memory, headers=hdrs)
    state = await tools_node(state)
    state = await generator_node_async(state, inference, headers=hdrs)
    state = safety_node(state)
    return state


def run_agent(
    query: Query,
    trace_id: str | None = None,
    **kwargs: Any,
) -> AgentState:
    """Sync wrapper. Prefer run_agent_async inside FastAPI handlers."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Nested loop (e.g. some test runners): force local fallback sync path
            return _run_agent_sync_local(query, trace_id)
        return loop.run_until_complete(run_agent_async(query, trace_id, **kwargs))
    except RuntimeError:
        return asyncio.run(run_agent_async(query, trace_id, **kwargs))


def _run_agent_sync_local(query: Query, trace_id: str | None = None) -> AgentState:
    """Deterministic local path for nested-loop contexts (unit tests under async)."""
    memory, inference = _clients(allow_local_fallback=True)
    state = _initial_state(query, trace_id)
    state = intent_classifier_node(state)

    lang = query.lang.value if isinstance(query.lang, Language) else str(query.lang)
    result = memory.retrieve_local(query.text, lang=lang)
    result["_backend"] = "local_fallback"
    state["citations"] = MemoryClient.parse_citations(result)
    state["confidence"] = float(result.get("confidence") or 0.5)
    state["retrieval_results"] = result

    intent = state.get("intent", "")
    tools: dict[str, Any] = {}
    if intent == "weather_advisory":
        tools["weather"] = {
            "district": "local",
            "forecast": "Light rain possible next 2 days; avoid spraying if wet foliage.",
            "source": "weather-stub",
        }
    if intent == "market_price":
        tools["market"] = {
            "crop": "cotton",
            "market": "Pune",
            "price": "Rs 7200/quintal",
            "source": "market-stub",
        }
    state["tool_outputs"] = tools

    prompt, evidence = _build_prompt(state)
    lang_s = lang
    gen = inference.generate_local(
        prompt,
        model_id=inference.default_model,
        intent=intent,
        lang=lang_s,
        evidence=evidence,
    )
    gen["_backend"] = "local_fallback"
    state["draft_answer"] = gen["completion"]
    state["model_version"] = gen.get("model_id") or inference.default_model
    base = float(state.get("confidence") or 0.5)
    cap = 0.90 if intent != "chemical_dosage" else 0.90
    if intent == "disease_diagnosis":
        cap = 0.88
    if intent == "chemical_dosage":
        cap = 0.90
    state["confidence"] = min(base, cap)
    state["retrieval_results"] = {
        **result,
        "_generation_backend": "local_fallback",
    }
    state = safety_node(state)
    return state


def state_to_response(state: AgentState) -> Response:
    q = state["query"]
    retrieval = state.get("retrieval_results") or {}
    meta = {
        "intent": state.get("intent"),
        "retrieval_backend": retrieval.get("_backend") if isinstance(retrieval, dict) else None,
        "generation_backend": retrieval.get("_generation_backend")
        if isinstance(retrieval, dict)
        else None,
    }
    return Response(
        response_id=str(uuid.uuid4()),
        query_id=q.query_id,
        answer=state.get("final_answer") or "",
        lang=q.lang,
        citations=state.get("citations") or [],
        confidence=float(state.get("confidence") or 0.0),
        model_version=state.get("model_version") or "unknown",
        trace_id=state.get("trace_id") or str(uuid.uuid4()),
        safety_level=SafetyLevel(state.get("safety_level") or "general"),
        safety_flags=state.get("safety_flags") or [],
        requires_review=bool(state.get("requires_review")),
        fallback_used=bool(state.get("fallback_used")),
        intent=state.get("intent"),
        action=state.get("action") or "answer",  # type: ignore[arg-type]
        metadata=meta,
    )
