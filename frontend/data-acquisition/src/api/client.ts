/** Data Acquisition API client — talks to data-ingestion-service */

const DEFAULT_BASE =
  import.meta.env.VITE_DAQ_API_BASE?.replace(/\/$/, "") || "/api";

export type SourceType =
  | "web"
  | "pdf"
  | "wikipedia"
  | "rss"
  | "json"
  | "image"
  | "audio"
  | "structured";

export type IngestMode = "auto" | "temporal" | "local";

export type AcqMode = "demo" | "real";

export interface IngestRequest {
  source_url: string;
  source_type?: SourceType;
  license?: string;
  content?: string | null;
  mode?: IngestMode;
  acq_mode?: AcqMode;
  run_id?: string | null;
  workflow?: string;
}

export interface ProgressInfo {
  percent: number;
  completed_count: number;
  total_stages: number;
  current_stage: string;
  completed_stages: string[];
  failed_stage?: string | null;
  partial?: boolean;
  checklist?: Array<{
    stage: string;
    done: boolean;
    failed?: boolean;
    data?: unknown;
  }>;
}

export interface JobRecord {
  job_id: string;
  status: string;
  source_url: string;
  source_type?: string;
  license?: string;
  created_at?: string;
  updated_at?: string;
  result?: Record<string, unknown> | null;
  progress?: ProgressInfo;
  qa_summary?: Record<string, unknown>;
  demo_name?: string;
  error?: string;
  run_id?: string;
  acq_mode?: string;
  failure_class?: string;
  stages_completed?: string[];
}

export interface Dashboard {
  generated_at: string;
  store_backend?: string;
  pipeline_stages?: string[];
  lakehouse_tables?: string[];
  kpis: Record<string, number | string | null | Record<string, number>>;
  quality_distribution: Record<string, number>;
  languages: Record<string, number>;
  source_types: Record<string, number>;
  quarantine_reasons: Record<string, number>;
  corpus: {
    status: string;
    documents: number;
    chunks: number;
    images: number;
    total_records: number;
    size_bytes: number;
    size_human: string;
    avg_quality: number | null;
    languages: Record<string, number>;
    manifests: number;
    latest_manifest_id?: string | null;
  };
  recent_jobs: JobRecord[];
  tables_counts: Record<string, number>;
}

export interface QaReport {
  report_id: string;
  generated_at: string;
  dashboard: Dashboard;
  qa_checklist: Array<{
    id: string;
    label: string;
    pass: boolean;
    info?: string;
  }>;
  qa_score_pct: number;
  samples?: Record<string, unknown[]>;
  recommendations: string[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${DEFAULT_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: DEFAULT_BASE,

  health: () =>
    request<{ status: string; service: string; jobs: number; version?: string }>(
      "/health"
    ),

  ingest: (body: IngestRequest) =>
    request<Record<string, unknown>>("/v1/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listJobs: (limit = 100) =>
    request<{ count: number; jobs: JobRecord[] }>(`/v1/jobs?limit=${limit}`),

  getJob: (id: string) => request<JobRecord>(`/v1/jobs/${id}`),

  discover: (body?: { candidates?: unknown[]; allow_list?: string[] }) =>
    request<{
      count: number;
      sources: Array<{
        source_url: string;
        source_type: string;
        license: string;
        allowed: boolean;
        reason?: string;
      }>;
    }>("/v1/discover", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),

  manifests: (limit = 50) =>
    request<{ manifests: unknown[] }>(`/v1/lakehouse/manifests?limit=${limit}`),

  table: (name: string, limit = 50) =>
    request<{ table: string; count: number; rows: unknown[] }>(
      `/v1/lakehouse/tables/${encodeURIComponent(name)}?limit=${limit}`
    ),

  stages: () =>
    request<{ stages: Array<{ key: string; label: string; order: number }> }>(
      "/v1/pipeline/stages"
    ),

  dashboard: (opts?: { acq_mode?: AcqMode; run_id?: string }) => {
    const q = new URLSearchParams();
    if (opts?.acq_mode) q.set("acq_mode", opts.acq_mode);
    if (opts?.run_id) q.set("run_id", opts.run_id);
    const qs = q.toString();
    return request<Dashboard>(`/v1/qa/dashboard${qs ? `?${qs}` : ""}`);
  },

  report: (includeSamples = true) =>
    request<QaReport>(
      `/v1/qa/report?include_samples=${includeSamples}&sample_limit=25`
    ),

  corpus: (
    limit = 100,
    opts?: { run_id?: string; acq_mode?: AcqMode }
  ) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (opts?.run_id) q.set("run_id", opts.run_id);
    if (opts?.acq_mode) q.set("acq_mode", opts.acq_mode);
    return request<{
      status: string;
      summary: Record<string, number | string>;
      documents: Array<Record<string, unknown>>;
      chunks_sample: Array<Record<string, unknown>>;
      images: Array<Record<string, unknown>>;
      manifests: Array<Record<string, unknown>>;
      run_id?: string;
      partial?: boolean;
    }>(`/v1/qa/corpus?${q.toString()}`);
  },

  quarantine: (limit = 100) =>
    request<{
      count: number;
      reasons: Record<string, number>;
      duplicate_count: number;
      records: Array<Record<string, unknown>>;
    }>(`/v1/qa/quarantine?limit=${limit}`),

  quality: (limit = 100) =>
    request<{
      count: number;
      tiers: Record<string, number>;
      avg_quality: number | null;
      records: Array<Record<string, unknown>>;
    }>(`/v1/qa/quality?limit=${limit}`),

  duplicates: (limit = 100) =>
    request<{
      count: number;
      records: Array<Record<string, unknown>>;
    }>(`/v1/qa/duplicates?limit=${limit}`),

  demoBatch: (includeQuarantine = true) =>
    request<{
      batch: string;
      acq_mode: string;
      run_id: string;
      paths?: Record<string, string>;
      count: number;
      results: Array<Record<string, unknown>>;
      dashboard: Dashboard;
    }>("/v1/qa/demo-batch", {
      method: "POST",
      body: JSON.stringify({
        include_quarantine_samples: includeQuarantine,
        mode: "local",
      }),
    }),

  catalog: (includeHeavy = true) =>
    request<{
      count: number;
      allow_list: string[];
      sources: Array<{
        source_url: string;
        source_type: string;
        license: string;
        title?: string;
        provider?: string;
      }>;
      note?: string;
    }>(`/v1/sources/catalog?include_heavy=${includeHeavy}`),

  /** Parallel REAL catalog batch (no example/demo sources) */
  realBatch: (opts?: {
    includeHeavy?: boolean;
    limit?: number;
    maxWorkers?: number;
    label?: string;
  }) =>
    request<{
      batch: string;
      run_id: string;
      acq_mode: string;
      count: number;
      workers: number;
      mode: string;
      paths?: Record<string, string>;
      jobs: Array<Record<string, unknown>>;
      note?: string;
    }>("/v1/ingest/batch", {
      method: "POST",
      body: JSON.stringify({
        use_catalog: true,
        include_heavy: opts?.includeHeavy ?? true,
        limit: opts?.limit ?? null,
        max_workers: opts?.maxWorkers ?? 4,
        mode: "local",
        acq_mode: "real",
        label: opts?.label ?? "real-catalog-batch",
      }),
    }),

  listRuns: (acq_mode?: AcqMode) =>
    request<{ count: number; runs: Array<Record<string, unknown>> }>(
      `/v1/runs${acq_mode ? `?acq_mode=${acq_mode}` : ""}`
    ),

  getRun: (runId: string) =>
    request<{
      run: Record<string, unknown>;
      outcome?: string;
      partial?: boolean;
      jobs_by_status?: Record<string, number>;
      jobs: JobRecord[];
      process_log: Array<Record<string, unknown>>;
      folder_tree: Array<Record<string, unknown>>;
    }>(`/v1/runs/${encodeURIComponent(runId)}`),

  runReport: (runId: string) =>
    request<{
      report_id: string;
      outcome: string;
      partial: boolean;
      summary: Record<string, unknown>;
      failures: Array<Record<string, unknown>>;
      success_jobs: Array<Record<string, unknown>>;
      partial_corpus: Record<string, unknown>;
      recommendations: string[];
      saved_path?: string;
    }>(`/v1/runs/${encodeURIComponent(runId)}/report`),

  runCorpus: (runId: string, limit = 100) =>
    request<{
      status: string;
      summary: Record<string, number | string>;
      documents: Array<Record<string, unknown>>;
      chunks_sample: Array<Record<string, unknown>>;
      run_id?: string;
    }>(`/v1/runs/${encodeURIComponent(runId)}/corpus?limit=${limit}`),

  /** Preview or execute cleanup (dry_run default true on server if omitted) */
  cleanup: (body: {
    dry_run?: boolean;
    confirm?: boolean;
    mode?: AcqMode | null;
    run_id?: string | null;
    older_than_hours?: number | null;
    keep_latest?: number;
    include_legacy_lakehouse?: boolean;
  }) =>
    request<Record<string, unknown>>("/v1/admin/cleanup", {
      method: "POST",
      body: JSON.stringify({
        dry_run: body.dry_run ?? true,
        confirm: body.confirm ?? false,
        mode: body.mode ?? null,
        run_id: body.run_id ?? null,
        older_than_hours: body.older_than_hours ?? null,
        keep_latest: body.keep_latest ?? 0,
        include_legacy_lakehouse: body.include_legacy_lakehouse ?? false,
      }),
    }),

  discoveryServices: () =>
    request<{
      services: Array<Record<string, unknown>>;
      categories: Array<{
        id: string;
        label: string;
        keyword_count: number;
        keywords: string[];
      }>;
      allow_list: string[];
      note?: string;
    }>("/v1/sources/discovery-services"),

  discoverOnline: (body: {
    query?: string;
    categories?: string[];
    keywords?: string[];
    pdf_only?: boolean;
    books_bias?: boolean;
    check_access?: boolean;
    max_results?: number;
    max_keywords?: number;
    auto_ingest?: boolean;
    auto_ingest_limit?: number;
  }) =>
    request<{
      count: number;
      allowed_count: number;
      reachable_count: number;
      pdf_count: number;
      keywords_used: string[];
      services_used: string[];
      discovery_services: Array<Record<string, unknown>>;
      sources: Array<Record<string, unknown>>;
      ingest_ready: Array<{
        source_url: string;
        source_type: string;
        license: string;
        title?: string;
        provider?: string;
      }>;
      auto_ingest?: { started: number; jobs: Array<Record<string, unknown>> };
      note?: string;
    }>("/v1/sources/discover-online", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Multilingual EN/HI/MR keyword discovery (plan service) */
  discoverKeywords: (body: {
    keywords: string[];
    languages?: string[];
    source_types?: string[];
    max_results?: number;
    check_access?: boolean;
    auto_ingest?: boolean;
    auto_ingest_limit?: number;
  }) =>
    request<{
      keywords: string[];
      languages: string[];
      expanded: Record<string, string[]>;
      count: number;
      sources: Array<Record<string, unknown>>;
      ingest_ready: Array<Record<string, unknown>>;
      auto_ingest?: { started: number; jobs: Array<Record<string, unknown>> };
      note?: string;
    }>("/v1/sources/discover-keywords", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Ingest discover-ready sources as REAL mode batch */
  ingestReadySources: (
    sources: Array<{
      source_url: string;
      source_type?: string;
      license?: string;
      title?: string;
      provider?: string;
    }>,
    label = "discover-real-ingest"
  ) =>
    request<{
      run_id: string;
      acq_mode: string;
      count: number;
      jobs: Array<Record<string, unknown>>;
      paths?: Record<string, string>;
    }>("/v1/ingest/batch", {
      method: "POST",
      body: JSON.stringify({
        acq_mode: "real",
        use_catalog: false,
        label,
        mode: "local",
        sources: sources.map((s) => ({
          source_url: s.source_url,
          source_type: s.source_type || "web",
          license: s.license || "unknown",
          title: s.title,
          provider: s.provider,
          acq_mode: "real",
          content: null,
          async_run: true,
          mode: "local",
        })),
      }),
    }),

  discoverPdfBooks: (topic: string, maxBooks = 10) =>
    request<{
      topic: string;
      count: number;
      sources: Array<Record<string, unknown>>;
    }>(
      `/v1/sources/discover-pdf-books?topic=${encodeURIComponent(topic)}&max_books=${maxBooks}`,
      { method: "POST" }
    ),

  checkAccess: (url: string) =>
    request<Record<string, unknown>>("/v1/sources/check-access", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
};

export function humanBytes(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  let x = Number(n);
  for (const unit of ["B", "KB", "MB", "GB"]) {
    if (Math.abs(x) < 1024) {
      return unit === "B" ? `${Math.round(x)} B` : `${x.toFixed(1)} ${unit}`;
    }
    x /= 1024;
  }
  return `${x.toFixed(2)} TB`;
}

export function statusTone(status: string | undefined): string {
  const s = (status || "").toLowerCase();
  if (s === "curated" || s === "image_stored") return "ok";
  if (s === "quarantine") return "warn";
  if (s === "failed") return "bad";
  if (s === "processing" || s === "queued") return "info";
  return "muted";
}
