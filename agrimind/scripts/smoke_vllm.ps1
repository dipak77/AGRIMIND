# Smoke-test local vLLM OpenAI-compatible API (and optional inference-service).
# Does not require GPU to *run this script* — only that vLLM is already up.
#
# Usage:
#   .\scripts\smoke_vllm.ps1
#   $env:VLLM_BASE="http://localhost:8008"; .\scripts\smoke_vllm.ps1
#   $env:INFERENCE_URL="http://localhost:8004"; .\scripts\smoke_vllm.ps1

$ErrorActionPreference = "Stop"

$VllmBase = if ($env:VLLM_BASE) { $env:VLLM_BASE } else { "http://localhost:8008" }
$ApiKey = if ($env:VLLM_API_KEY) { $env:VLLM_API_KEY } else { "EMPTY" }
$Model = if ($env:VLLM_MODEL) { $env:VLLM_MODEL } else { "Qwen/Qwen2.5-0.5B-Instruct" }
$InferenceUrl = $env:INFERENCE_URL

$headers = @{
    Authorization = "Bearer $ApiKey"
    "Content-Type" = "application/json"
}

Write-Host "==> vLLM models: $VllmBase/v1/models"
$models = Invoke-RestMethod -Uri "$VllmBase/v1/models" -Headers @{ Authorization = "Bearer $ApiKey" } -Method Get
$models | ConvertTo-Json -Depth 6 -Compress | ForEach-Object { $_.Substring(0, [Math]::Min(500, $_.Length)) }
Write-Host ""

Write-Host "==> vLLM chat completions (tiny)"
$chatBody = @{
    model = $Model
    messages = @(@{ role = "user"; content = "Say ok in one word." })
    max_tokens = 8
    temperature = 0
} | ConvertTo-Json -Depth 5

$chat = Invoke-RestMethod -Uri "$VllmBase/v1/chat/completions" -Headers $headers -Method Post -Body $chatBody
$chat | ConvertTo-Json -Depth 6 -Compress | ForEach-Object { $_.Substring(0, [Math]::Min(800, $_.Length)) }
Write-Host ""

if ($InferenceUrl) {
    Write-Host "==> inference-service generate: $InferenceUrl/v1/generate"
    $genBody = @{
        prompt = "What is crop rotation? One sentence."
        max_tokens = 64
        temperature = 0.2
    } | ConvertTo-Json

    $gen = Invoke-RestMethod -Uri "$InferenceUrl/v1/generate" `
        -Headers @{ "Content-Type" = "application/json" } `
        -Method Post -Body $genBody
    $gen | ConvertTo-Json -Depth 6 -Compress | ForEach-Object { $_.Substring(0, [Math]::Min(800, $_.Length)) }
    Write-Host ""
    if ($gen.simulated -eq $true) {
        Write-Warning "inference-service still simulated — set INFERENCE_MODE=remote and VLLM_BASE_URL=$VllmBase/v1"
    }
}
else {
    Write-Host "==> skip inference-service (set INFERENCE_URL=http://localhost:8004 to enable)"
}

Write-Host "OK: vLLM smoke passed"
