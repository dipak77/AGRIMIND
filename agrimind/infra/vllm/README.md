# GPU vLLM deployment (AGRIMIND)

Package **OpenAI-compatible** vLLM so `inference-service` can use a real LLM via
`OpenAICompatBackend` (`INFERENCE_MODE=remote` / `VLLM_BASE_URL`).

**Weights are not bundled.** The container downloads models from Hugging Face on first start.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| NVIDIA GPU | CUDA-capable; VRAM must fit `VLLM_MODEL` + KV cache |
| NVIDIA driver | Host driver installed and working (`nvidia-smi`) |
| NVIDIA Container Toolkit | [install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) |
| Docker Compose v2 | `docker compose version` |
| Disk | HF cache volume; small smoke models ~1–2 GB; 7B models tens of GB |

### Verify host GPU

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

Windows: Docker Desktop → Settings → Resources → enable GPU; WSL2 backend recommended.

---

## Start vLLM

From the repo root (`agrimind/`):

```bash
# Optional: choose model / API key
export VLLM_MODEL=Qwen/Qwen2.5-0.5B-Instruct   # smoke default
export VLLM_API_KEY=EMPTY
# export HUGGING_FACE_HUB_TOKEN=hf_...          # only for gated models

docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu up -d vllm
```

**Windows (PowerShell):**

```powershell
$env:VLLM_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
$env:VLLM_API_KEY = "EMPTY"
docker compose -f docker-compose.yml -f docker-compose.vllm.yml --profile gpu up -d vllm
```

**Makefile (Linux/macOS):**

```bash
make vllm-up
make vllm-smoke
make vllm-down
```

| Item | Value |
|---|---|
| Host API | `http://localhost:8008` |
| OpenAI base | `http://localhost:8008/v1` |
| Default model (smoke) | `Qwen/Qwen2.5-0.5B-Instruct` |
| Compose profile | `gpu` (plain `docker compose up` stays CPU-only) |

Production / larger models: set `VLLM_MODEL` (e.g. `Qwen/Qwen2.5-7B-Instruct`) and raise
`VLLM_MAX_MODEL_LEN` / lower `VLLM_GPU_MEMORY_UTILIZATION` as needed. Do not ship large
weights in the monorepo.

---

## Wire inference-service

`packages/models/inference/backends.py` → `OpenAICompatBackend` posts to
`{VLLM_BASE_URL}/chat/completions`.

### Host process (local uvicorn)

```bash
export INFERENCE_MODE=remote
export VLLM_BASE_URL=http://localhost:8008/v1
export VLLM_API_KEY=EMPTY
# Prefer the same id the server loaded:
export DEFAULT_CLOUD_MODEL=Qwen/Qwen2.5-0.5B-Instruct

uv run uvicorn inference_service.main:app --app-dir services/inference-service --port 8004
```

### Compose network

If `inference-service` runs in the same compose project as `vllm`:

```bash
INFERENCE_MODE=remote
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_API_KEY=EMPTY
```

(`docker-compose.yml` does not enable this by default so CPU stacks stay sim-backend.)

### Modes

| `INFERENCE_MODE` | Behavior |
|---|---|
| `auto` | Remote if `VLLM_BASE_URL` set, else grounded sim |
| `remote` | Require `VLLM_BASE_URL`; fail if missing |
| `sim` | Always grounded sim (no GPU) |

---

## Smoke tests

```bash
# bash
./scripts/smoke_vllm.sh

# PowerShell
./scripts/smoke_vllm.ps1

# or
make vllm-smoke
```

Scripts hit:

1. `GET http://localhost:8008/v1/models`
2. `POST http://localhost:8008/v1/chat/completions` (tiny prompt)
3. Optionally `POST http://localhost:8004/v1/generate` if inference-service is up in remote mode

---

## Environment reference

| Variable | Default | Purpose |
|---|---|---|
| `VLLM_MODEL` | `Qwen/Qwen2.5-0.5B-Instruct` | HF model id served by vLLM |
| `VLLM_IMAGE` | `vllm/vllm-openai:latest` | Container image (pin in prod) |
| `VLLM_API_KEY` | `EMPTY` | OpenAI-style API key for vLLM |
| `VLLM_HOST_PORT` | `8008` | Host port → container `8000` |
| `VLLM_DTYPE` | `auto` | vLLM `--dtype` |
| `VLLM_MAX_MODEL_LEN` | `2048` | Context length (lower = less VRAM) |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.90` | Fraction of GPU memory for vLLM |
| `HUGGING_FACE_HUB_TOKEN` | _(empty)_ | Gated model access |
| `VLLM_BASE_URL` | — | Client URL for inference-service |
| `INFERENCE_MODE` | `auto` | `auto` \| `sim` \| `remote` |

See also root `.env.example`.

---

## Troubleshooting

### GPU not visible in container

- Host: `nvidia-smi` must work.
- Toolkit: reinstall [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) and restart Docker.
- Confirm: `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`
- WSL2: update GPU drivers on Windows; enable WSL integration in Docker Desktop.

### Out of memory (OOM)

- Use a smaller model (`VLLM_MODEL=Qwen/Qwen2.5-0.5B-Instruct` or `facebook/opt-125m`).
- Lower `VLLM_MAX_MODEL_LEN` (e.g. `1024` or `512`).
- Lower `VLLM_GPU_MEMORY_UTILIZATION` (e.g. `0.7`).
- Close other GPU processes.

### Model download failures

- Check network / proxy from the container.
- Set `HUGGING_FACE_HUB_TOKEN` for gated repos.
- Inspect logs: `docker logs agrimind-vllm`
- Cache volume `vllm-hf-cache` holds downloads; free disk if full.

### API auth errors (401)

- Match keys: server `--api-key` / `VLLM_API_KEY` and client `VLLM_API_KEY`.
- Smoke scripts send `Authorization: Bearer $VLLM_API_KEY` (default `EMPTY`).

### inference-service still `simulated: true`

- Ensure `VLLM_BASE_URL` is set **before** process start.
- Prefer `INFERENCE_MODE=remote`.
- Check `GET http://localhost:8004/health` → `"mode": "remote"`, `"backend": "openai_compat"`.
- From the host, `VLLM_BASE_URL=http://localhost:8008/v1` (not `http://vllm:8000`).

### Healthcheck flapping on first boot

- First model download can exceed `start_period` (5 min). Wait and re-check logs.
- `docker compose ... up` without `-d` to watch progress.

---

## Optional Kubernetes

Minimal Deployment with one GPU:

```bash
kubectl apply -f infra/k8s/overlays/gpu/vllm-deployment.yaml
```

See [`infra/k8s/overlays/gpu/vllm-deployment.yaml`](../k8s/overlays/gpu/vllm-deployment.yaml).
Point inference-service at `http://vllm:8000/v1` inside the cluster
(`VLLM_BASE_URL`, `INFERENCE_MODE=remote`).

Cluster needs NVIDIA device plugin (`nvidia.com/gpu` resource).
