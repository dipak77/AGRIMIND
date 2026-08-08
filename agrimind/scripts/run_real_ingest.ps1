# Start data-ingestion-service (if needed) and kick off real agri sources in parallel.
# Usage (from repo root or agrimind/):
#   pwsh agrimind/scripts/run_real_ingest.ps1
#   pwsh agrimind/scripts/run_real_ingest.ps1 -Port 8017 -Limit 10

param(
    [int]$Port = 8017,
    [int]$Limit = 10,
    [int]$Workers = 4,
    [switch]$NoStart,
    # Optional: discover EN/HI/MR keywords first, then ingest those hits
    [string]$DiscoverKeywords = "",
    [string]$Langs = "en,hi,mr",
    [switch]$DiscoverOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $Root "agrimind"))) {
    $Root = Split-Path $PSScriptRoot -Parent  # already inside agrimind
    $Agri = $Root
} else {
    $Agri = Join-Path $Root "agrimind"
}

$env:OBJECT_STORE = "local"
$env:LAKEHOUSE_ROOT = "data/lakehouse"
$env:INDEX_ON_INGEST = if ($env:INDEX_ON_INGEST) { $env:INDEX_ON_INGEST } else { "false" }
$env:INGEST_WORKERS = "$Workers"
$env:SKIP_ROBOTS = if ($env:SKIP_ROBOTS) { $env:SKIP_ROBOTS } else { "true" }

$base = "http://127.0.0.1:$Port"

function Test-Health {
    try {
        $h = Invoke-RestMethod "$base/health" -TimeoutSec 2
        return $h.status -eq "healthy"
    } catch { return $false }
}

if (-not (Test-Health) -and -not $NoStart) {
    Write-Host "Starting data-ingestion-service on $Port ..."
    $uvArgs = @(
        "run", "uvicorn", "data_ingestion_service.main:app",
        "--host", "127.0.0.1", "--port", "$Port",
        "--app-dir", "services/data-ingestion-service"
    )
    Start-Process -FilePath "uv" -ArgumentList $uvArgs -WorkingDirectory $Agri -WindowStyle Minimized
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Health) { $ok = $true; break }
    }
    if (-not $ok) { throw "Service did not become healthy on $base" }
}

if ($DiscoverKeywords) {
    Write-Host "Multilingual discover: $DiscoverKeywords (langs=$Langs)"
    $kwList = @($DiscoverKeywords -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $langList = @($Langs -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $discBody = @{
        keywords     = $kwList
        languages    = $langList
        check_access = $false
        max_results  = [Math]::Max($Limit, 15)
        auto_ingest  = -not $DiscoverOnly
        auto_ingest_limit = $Limit
    } | ConvertTo-Json
    $disc = Invoke-RestMethod -Uri "$base/v1/sources/discover-keywords" -Method POST -Body $discBody -ContentType "application/json"
    Write-Host "Discovered $($disc.count) sources (expanded HI/MR included)."
    $disc.sources | Select-Object -First 12 | ForEach-Object {
        "  [$($_.language)] trust=$($_.trust_score) $($_.source_type) — $($_.title)"
    }
    if ($DiscoverOnly) {
        Write-Host "DiscoverOnly set — skipping catalog batch ingest."
        exit 0
    }
    if ($disc.auto_ingest) {
        Write-Host "Auto-ingest started: $($disc.auto_ingest.started) jobs"
    }
} else {
    Write-Host "Catalog:"
    $cat = Invoke-RestMethod "$base/v1/sources/catalog"
    $cat.sources | ForEach-Object { "  [$($_.provider)] $($_.source_type) — $($_.title)" }

    Write-Host "`nStarting parallel real batch (limit=$Limit workers=$Workers)..."
    $body = @{
        use_catalog   = $true
        include_heavy = $true
        max_workers   = $Workers
        mode          = "local"
        limit         = $Limit
    } | ConvertTo-Json
    $batch = Invoke-RestMethod -Uri "$base/v1/ingest/batch" -Method POST -Body $body -ContentType "application/json"
    Write-Host "Queued $($batch.count) jobs. Poll $base/v1/qa/dashboard or open the DAQ UI Live Jobs tab."
    $batch.jobs | ForEach-Object { "  $($_.job_id) $($_.provider) $($_.source_type)" }
}

# Brief live progress preview
for ($i = 1; $i -le 8; $i++) {
    Start-Sleep -Seconds 3
    $jobs = Invoke-RestMethod "$base/v1/jobs?limit=50"
    $by = @{}
    foreach ($j in $jobs.jobs) {
        if (-not $by.ContainsKey($j.status)) { $by[$j.status] = 0 }
        $by[$j.status]++
    }
    $line = ($by.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "
    Write-Host ("t={0}s  {1}" -f ($i * 3), $line)
    $busy = ($by["processing"] + $by["queued"])
    if (-not $busy) { break }
}

try {
    $d = Invoke-RestMethod "$base/v1/qa/dashboard"
    Write-Host "`nDashboard: curated=$($d.kpis.curated_documents) chunks=$($d.kpis.curated_chunks) size=$($d.corpus.size_human) store=$($d.store_backend)"
} catch {
    Write-Host "Dashboard poll: $_"
}

Write-Host "`nDone. UI: frontend data-acquisition (proxy → $base). API docs: $base/docs"
