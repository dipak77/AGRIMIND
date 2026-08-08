#!/usr/bin/env bash
# Smoke-test local vLLM OpenAI-compatible API (and optional inference-service).
# Does not require GPU to *run this script* — only that vLLM is already up.
#
# Usage:
#   ./scripts/smoke_vllm.sh
#   VLLM_BASE=http://localhost:8008 VLLM_API_KEY=EMPTY ./scripts/smoke_vllm.sh
#   INFERENCE_URL=http://localhost:8004 ./scripts/smoke_vllm.sh   # also hit /v1/generate

set -euo pipefail

VLLM_BASE="${VLLM_BASE:-http://localhost:8008}"
VLLM_API_KEY="${VLLM_API_KEY:-EMPTY}"
VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
INFERENCE_URL="${INFERENCE_URL:-}"
AUTH_HEADER="Authorization: Bearer ${VLLM_API_KEY}"

echo "==> vLLM models: ${VLLM_BASE}/v1/models"
MODELS_JSON="$(curl -sfS -H "${AUTH_HEADER}" "${VLLM_BASE}/v1/models")"
echo "${MODELS_JSON}" | head -c 500
echo ""

echo "==> vLLM chat completions (tiny)"
CHAT_JSON="$(curl -sfS -X POST "${VLLM_BASE}/v1/chat/completions" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${VLLM_MODEL}\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Say ok in one word.\"}],
    \"max_tokens\": 8,
    \"temperature\": 0
  }")"
echo "${CHAT_JSON}" | head -c 800
echo ""

if [[ -n "${INFERENCE_URL}" ]]; then
  echo "==> inference-service generate: ${INFERENCE_URL}/v1/generate"
  GEN_JSON="$(curl -sfS -X POST "${INFERENCE_URL}/v1/generate" \
    -H "Content-Type: application/json" \
    -d "{
      \"prompt\": \"What is crop rotation? One sentence.\",
      \"max_tokens\": 64,
      \"temperature\": 0.2
    }")"
  echo "${GEN_JSON}" | head -c 800
  echo ""
  if echo "${GEN_JSON}" | grep -q '"simulated"[[:space:]]*:[[:space:]]*true'; then
    echo "WARN: inference-service still simulated — set INFERENCE_MODE=remote and VLLM_BASE_URL=${VLLM_BASE}/v1" >&2
  fi
else
  echo "==> skip inference-service (set INFERENCE_URL=http://localhost:8004 to enable)"
fi

echo "OK: vLLM smoke passed"
