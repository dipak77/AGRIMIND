import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  humanBytes,
  type Dashboard,
  type IngestMode,
  type JobRecord,
  type QaReport,
  type SourceType,
} from "./api/client";
import { BarChart, Empty, KpiCard, Pill, ProgressBar, ScoreRing, Toast } from "./components/ui";
import { usePolling } from "./hooks/usePolling";

type TabId =
  | "dashboard"
  | "discover"
  | "ingest"
  | "monitor"
  | "corpus"
  | "quality"
  | "quarantine"
  | "duplicates"
  | "report"
  | "lakehouse";

const NAV: Array<{ id: TabId; icon: string; label: string }> = [
  { id: "dashboard", icon: "◉", label: "Command Center" },
  { id: "discover", icon: "⌕", label: "Discover Sources" },
  { id: "ingest", icon: "＋", label: "Ingest Source" },
  { id: "monitor", icon: "↻", label: "Live Jobs" },
  { id: "corpus", icon: "▣", label: "Ready Corpus" },
  { id: "quality", icon: "★", label: "Data Quality" },
  { id: "quarantine", icon: "⚠", label: "Quarantine" },
  { id: "duplicates", icon: "⧉", label: "Duplicates" },
  { id: "report", icon: "☰", label: "QA Report" },
  { id: "lakehouse", icon: "▤", label: "Lakehouse" },
];

const SOURCE_TYPES: SourceType[] = [
  "web",
  "pdf",
  "wikipedia",
  "rss",
  "json",
  "image",
  "audio",
  "structured",
];

const LICENSES = [
  "cc-by",
  "cc-by-sa",
  "cc0",
  "government_open",
  "unknown",
  "restricted",
];

function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && !Number.isNaN(v) ? v : fallback;
}

export default function App() {
  const [tab, setTab] = useState<TabId>("dashboard");
  const [pollMs, setPollMs] = useState(3000);
  const [live, setLive] = useState(true);
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "bad" } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [selectedJob, setSelectedJob] = useState<JobRecord | null>(null);
  const [acqMode, setAcqMode] = useState<"demo" | "real">("real");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const fetchDash = useCallback(
    () =>
      api.dashboard({
        acq_mode: acqMode,
        run_id: activeRunId || undefined,
      }),
    [acqMode, activeRunId]
  );
  const {
    data: dash,
    error: dashErr,
    loading: dashLoading,
    lastUpdated,
    refresh: refreshDash,
  } = usePolling<Dashboard>(fetchDash, pollMs, live);

  const healthPoll = useCallback(() => api.health(), []);
  const { data: health } = usePolling(healthPoll, 8000, live);

  const showToast = (msg: string, tone: "ok" | "bad" = "ok") => {
    setToast({ msg, tone });
    window.setTimeout(() => setToast(null), 4500);
  };

  const runDemo = async () => {
    setBusy(true);
    try {
      setAcqMode("demo");
      const res = await api.demoBatch(true);
      setActiveRunId(res.run_id || null);
      await refreshDash();
      showToast(
        `DEMO run ${res.run_id}: ${res.count} mock jobs (isolated folder).`,
        "ok"
      );
      setTab("monitor");
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setBusy(false);
    }
  };

  const runRealBatch = async () => {
    setBusy(true);
    try {
      setAcqMode("real");
      const res = await api.realBatch({
        includeHeavy: true,
        maxWorkers: 4,
        label: "ui-real-catalog",
      });
      setActiveRunId(res.run_id || null);
      await refreshDash();
      showToast(
        `REAL run ${res.run_id}: ${res.count} trusted sources (no example/demo).`,
        "ok"
      );
      setLive(true);
      setTab("monitor");
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setBusy(false);
    }
  };

  const runCleanup = async (confirmDelete: boolean) => {
    setBusy(true);
    try {
      const res = await api.cleanup({
        dry_run: !confirmDelete,
        confirm: confirmDelete,
        mode: acqMode,
        keep_latest: confirmDelete ? 0 : 0,
        include_legacy_lakehouse: confirmDelete,
      });
      const freed =
        (res.total_freed_human as string) ||
        (res.freed_human as string) ||
        (res.would_delete_human as string) ||
        String(res.total_freed_bytes ?? res.would_delete_bytes ?? "—");
      showToast(
        confirmDelete
          ? `Cleanup done (${acqMode}): freed ${freed}`
          : `Cleanup preview (${acqMode}): would free ${freed}`,
        "ok"
      );
      if (confirmDelete) {
        setActiveRunId(null);
        await refreshDash();
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setBusy(false);
    }
  };

  const kpis = dash?.kpis || {};

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <h1>AGRIMIND DAQ</h1>
            <p>Data Acquisition · Phase 2</p>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={tab === n.id ? "active" : ""}
              onClick={() => setTab(n.id)}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {live ? <span className="live-dot" /> : null}
            <span>{live ? "Live polling" : "Paused"} · {pollMs / 1000}s</span>
          </div>
          <div>
            API: <span className="mono">{api.base}</span>
          </div>
          <div>
            Service:{" "}
            {health ? (
              <Pill status="curated">{health.status}</Pill>
            ) : (
              <Pill status="failed">offline</Pill>
            )}
          </div>
          <div>Store: {dash?.store_backend || "—"}</div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <h2>{NAV.find((n) => n.id === tab)?.label}</h2>
            <p className="sub">
              Full-stack transparency for QA: stages, quality, duplicates,
              quarantine, and ready corpus metrics.
              {lastUpdated
                ? ` · Updated ${new Date(lastUpdated).toLocaleTimeString()}`
                : ""}
            </p>
          </div>
          <div className="top-actions">
            <select
              className="btn"
              value={acqMode}
              onChange={(e) => {
                setAcqMode(e.target.value as "demo" | "real");
                setActiveRunId(null);
              }}
              title="Acquisition mode"
            >
              <option value="real">REAL mode</option>
              <option value="demo">DEMO mode</option>
            </select>
            <label className="pill" style={{ cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={live}
                onChange={(e) => setLive(e.target.checked)}
              />{" "}
              Live
            </label>
            <select
              className="btn"
              value={pollMs}
              onChange={(e) => setPollMs(Number(e.target.value))}
              title="Poll interval"
            >
              <option value={2000}>2s</option>
              <option value={3000}>3s</option>
              <option value={5000}>5s</option>
              <option value={10000}>10s</option>
            </select>
            <button className="btn" onClick={() => refreshDash()} disabled={busy}>
              Refresh
            </button>
            <button
              className="btn"
              onClick={runDemo}
              disabled={busy}
              title="Isolated demo run with example.com mocks only"
            >
              {busy ? "Running…" : "Demo batch"}
            </button>
            <button
              className="btn primary"
              onClick={runRealBatch}
              disabled={busy}
              title="Trusted catalog only — no example/demo data"
            >
              {busy ? "Starting…" : "▶ Real sources"}
            </button>
            <button
              className="btn"
              onClick={() => runCleanup(false)}
              disabled={busy}
              title="Preview cleanup size"
            >
              Cleanup preview
            </button>
            <button
              className="btn"
              onClick={() => {
                if (
                  window.confirm(
                    `Delete ${acqMode} run data + legacy lakehouse? This frees disk space.`
                  )
                ) {
                  void runCleanup(true);
                }
              }}
              disabled={busy}
              title="Delete generated data"
            >
              Reset cleanup
            </button>
          </div>
        </div>
        <div className="sub" style={{ marginTop: 6 }}>
          Mode: <strong>{acqMode.toUpperCase()}</strong>
          {activeRunId ? (
            <>
              {" "}
              · runId: <span className="mono">{activeRunId}</span>
            </>
          ) : null}
          {acqMode === "real" ? (
            <span className="faint">
              {" "}
              — trusted live sources only (no example.com / no inline mock)
            </span>
          ) : (
            <span className="faint">
              {" "}
              — mock/example sources for QA only (isolated under data/runs/demo-*)
            </span>
          )}
        </div>

        {dashErr ? (
          <div className="alert bad">
            Cannot reach data-ingestion-service ({dashErr}). Start it (port
            8017 default for DAQ UI), then ensure Vite proxy{" "}
            <span className="mono">/api</span> is up.{" "}
            <span className="mono">
              cd agrimind; $env:OBJECT_STORE=&quot;local&quot;; uv run uvicorn
              data_ingestion_service.main:app --port 8017 --app-dir
              services/data-ingestion-service
            </span>
          </div>
        ) : null}

        {tab === "dashboard" && (
          <DashboardView dash={dash} loading={dashLoading} onOpenJob={setSelectedJob} />
        )}
        {tab === "discover" && (
          <DiscoverView
            onToast={showToast}
            onIngestStarted={async () => {
              await refreshDash();
              setTab("monitor");
            }}
          />
        )}
        {tab === "ingest" && (
          <IngestView
            onDone={async () => {
              await refreshDash();
              setTab("monitor");
            }}
            onToast={showToast}
          />
        )}
        {tab === "monitor" && (
          <MonitorView
            jobs={dash?.recent_jobs || []}
            selected={selectedJob}
            onSelect={setSelectedJob}
            onRefresh={refreshDash}
            activeRunId={activeRunId}
            onToast={showToast}
          />
        )}
        {tab === "corpus" && (
          <CorpusView runId={activeRunId} acqMode={acqMode} />
        )}
        {tab === "quality" && <QualityView />}
        {tab === "quarantine" && <QuarantineView />}
        {tab === "duplicates" && <DuplicatesView />}
        {tab === "report" && (
          <ReportView activeRunId={activeRunId} onToast={showToast} />
        )}
        {tab === "lakehouse" && <LakehouseView tables={dash?.tables_counts} />}
      </main>

      {toast ? (
        <Toast
          message={toast.msg}
          tone={toast.tone}
          onClose={() => setToast(null)}
        />
      ) : null}
    </div>
  );
}

function DashboardView({
  dash,
  loading,
  onOpenJob,
}: {
  dash: Dashboard | null;
  loading: boolean;
  onOpenJob: (j: JobRecord) => void;
}) {
  if (loading && !dash) return <Empty>Loading dashboard…</Empty>;
  if (!dash) return <Empty>No dashboard data yet.</Empty>;
  const k = dash.kpis;
  return (
    <div className="grid">
      <div className="grid kpis">
        <KpiCard
          label="Success rate"
          value={`${num(k.success_rate_pct)}%`}
          meta="Curated / (curated + quarantine)"
          accent="var(--ok)"
        />
        <KpiCard
          label="Quarantine rate"
          value={`${num(k.quarantine_rate_pct)}%`}
          meta={`${num(k.quarantine_records)} records`}
          accent="var(--warn)"
        />
        <KpiCard
          label="Duplicate rate"
          value={`${num(k.duplicate_rate_pct)}%`}
          meta={`${num(k.duplicates_detected)} near/exact dups`}
          accent="var(--purple)"
        />
        <KpiCard
          label="Avg quality"
          value={
            k.avg_quality_score != null
              ? Number(k.avg_quality_score).toFixed(2)
              : "—"
          }
          meta="Curated docs only"
          accent="var(--info)"
        />
        <KpiCard
          label="Ready corpus"
          value={String(num(k.ready_corpus_records))}
          meta={humanBytes(num(k.ready_corpus_bytes))}
        />
        <KpiCard
          label="Jobs"
          value={String(num(k.jobs_total))}
          meta={`Raw ${num(k.raw_documents)} · Curated ${num(k.curated_documents)}`}
        />
      </div>

      <div className="grid two">
        <div className="card">
          <h3>
            Pipeline health
            <Pill status="curated">{dash.corpus.status}</Pill>
          </h3>
          <p className="hint">
            Lake tables, corpus size, and quality tiers for transparent QA.
          </p>
          <div className="detail-grid" style={{ marginBottom: 14 }}>
            <div>
              <div className="k">Documents</div>
              <div className="v">{dash.corpus.documents}</div>
            </div>
            <div>
              <div className="k">Chunks</div>
              <div className="v">{dash.corpus.chunks}</div>
            </div>
            <div>
              <div className="k">Images</div>
              <div className="v">{dash.corpus.images}</div>
            </div>
            <div>
              <div className="k">Size</div>
              <div className="v">{dash.corpus.size_human}</div>
            </div>
            <div>
              <div className="k">Manifests</div>
              <div className="v">{dash.corpus.manifests}</div>
            </div>
            <div>
              <div className="k">PII redacted</div>
              <div className="v">{num(k.pii_redacted_docs)}</div>
            </div>
          </div>
          <h3>Quality tiers</h3>
          <BarChart data={dash.quality_distribution} color="var(--accent)" />
        </div>

        <div className="card">
          <h3>Quarantine reasons</h3>
          <BarChart data={dash.quarantine_reasons} color="var(--warn)" />
          <h3 style={{ marginTop: 16 }}>Languages</h3>
          <BarChart data={dash.languages} color="var(--info)" />
          <h3 style={{ marginTop: 16 }}>Source types</h3>
          <BarChart data={dash.source_types} color="var(--purple)" />
        </div>
      </div>

      <div className="card">
        <h3>Recent jobs (live)</h3>
        <JobsTable jobs={dash.recent_jobs} onSelect={onOpenJob} />
      </div>
    </div>
  );
}

function JobsTable({
  jobs,
  onSelect,
}: {
  jobs: JobRecord[];
  onSelect?: (j: JobRecord) => void;
}) {
  if (!jobs.length) {
    return (
      <Empty>
        No jobs yet. Use <strong>Seed QA Demo Batch</strong> or Ingest Source.
      </Empty>
    );
  }
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Job</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Source</th>
            <th>QA</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => {
            // Never show 100% for failed/quarantine (stale snapshots or old API)
            let pct = j.progress?.percent ?? 0;
            if (
              (j.status === "failed" || j.status === "quarantine") &&
              pct >= 100
            ) {
              const done = j.progress?.completed_count ?? 0;
              const total = j.progress?.total_stages ?? 16;
              pct = Math.min(99, Math.round((100 * done) / total) || 12);
            }
            const stage =
              j.progress?.failed_stage ||
              j.progress?.current_stage ||
              (j.status === "failed" ? "failed" : "—");
            const qs = j.qa_summary || {};
            const err =
              (qs.error as string | undefined) ||
              j.error ||
              (j.result?.error as string | undefined);
            return (
              <tr
                key={j.job_id}
                style={{ cursor: onSelect ? "pointer" : undefined }}
                onClick={() => onSelect?.(j)}
              >
                <td className="mono">{j.job_id}</td>
                <td>
                  <Pill status={j.status}>{j.status}</Pill>
                  {j.failure_class || qs.failure_class ? (
                    <div className="faint mono">
                      {String(j.failure_class || qs.failure_class)}
                    </div>
                  ) : null}
                </td>
                <td style={{ minWidth: 140 }}>
                  <div style={{ marginBottom: 4 }} className="mono">
                    {pct}% · {stage}
                    {j.progress?.partial || j.status === "failed"
                      ? " · partial"
                      : ""}
                  </div>
                  <ProgressBar
                    percent={pct}
                    tone={
                      j.status === "failed"
                        ? "bad"
                        : j.status === "quarantine"
                          ? "warn"
                          : ""
                    }
                  />
                  {err ? (
                    <div className="faint" style={{ marginTop: 4, fontSize: 11 }}>
                      {String(err).slice(0, 90)}
                    </div>
                  ) : null}
                </td>
                <td>
                  <div className="mono" style={{ maxWidth: 260 }}>
                    {(j.source_url || "").slice(0, 48)}
                    {(j.source_url || "").length > 48 ? "…" : ""}
                  </div>
                  <div className="faint">
                    {j.source_type || "web"}
                    {j.demo_name ? ` · ${j.demo_name}` : ""}
                  </div>
                </td>
                <td className="mono">
                  q=
                  {qs.quality_score != null
                    ? Number(qs.quality_score).toFixed(2)
                    : "—"}
                  <br />
                  {qs.error ? (
                    <span style={{ color: "var(--warn)" }}>
                      {String(qs.error).slice(0, 40)}
                    </span>
                  ) : (
                    <span className="faint">
                      {String(qs.language ?? "—")} · chunks{" "}
                      {String(qs.chunk_count ?? "—")}
                    </span>
                  )}
                </td>
                <td className="faint">
                  {j.updated_at
                    ? new Date(j.updated_at).toLocaleTimeString()
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DiscoverView({
  onToast,
  onIngestStarted,
}: {
  onToast: (m: string, t?: "ok" | "bad") => void;
  onIngestStarted: () => void;
}) {
  const [query, setQuery] = useState("soil health irrigation farmers");
  const [books, setBooks] = useState(true);
  const [pdfOnly, setPdfOnly] = useState(false);
  const [checkAccess, setCheckAccess] = useState(true);
  const [autoIngest, setAutoIngest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [langs, setLangs] = useState<string[]>(["en", "hi", "mr"]);
  const [useMultilingual, setUseMultilingual] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, string[]> | null>(
    null
  );
  const [cats, setCats] = useState<string[]>([
    "soil_health",
    "irrigation_water",
    "crops",
    "pests_ipm",
    "agri_books_reference",
  ]);
  const [servicesMeta, setServicesMeta] = useState<
    Array<Record<string, unknown>>
  >([]);
  const [taxonomy, setTaxonomy] = useState<
    Array<{ id: string; label: string; keywords: string[] }>
  >([]);
  const [result, setResult] = useState<{
    count: number;
    allowed_count: number;
    reachable_count: number;
    pdf_count: number;
    keywords_used: string[];
    sources: Array<Record<string, unknown>>;
    ingest_ready: Array<Record<string, unknown>>;
    discovery_services?: Array<Record<string, unknown>>;
    auto_ingest?: { started: number };
  } | null>(null);

  useEffect(() => {
    api
      .discoveryServices()
      .then((r) => {
        setServicesMeta(r.services || []);
        setTaxonomy(
          (r.categories || []).map((c) => ({
            id: c.id,
            label: c.label,
            keywords: c.keywords || [],
          }))
        );
      })
      .catch(() => {
        /* offline */
      });
  }, []);

  const toggleCat = (id: string) => {
    setCats((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleLang = (id: string) => {
    setLangs((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const run = async () => {
    setBusy(true);
    try {
      if (useMultilingual) {
        const kws = query
          .split(/[,;]+/)
          .map((s) => s.trim())
          .filter(Boolean);
        const res = await api.discoverKeywords({
          keywords: kws.length ? kws : [query],
          languages: langs.length ? langs : ["en", "hi", "mr"],
          source_types: pdfOnly
            ? ["pdf"]
            : books
              ? ["wikipedia", "pdf", "web"]
              : ["wikipedia", "web", "pdf"],
          max_results: 40,
          check_access: checkAccess,
          auto_ingest: autoIngest,
          auto_ingest_limit: 8,
        });
        setExpanded(res.expanded || null);
        setResult({
          count: res.count,
          allowed_count: res.count,
          reachable_count: res.sources.filter(
            (s) => (s.access_status as string) === "ok"
          ).length,
          pdf_count: res.sources.filter((s) => s.source_type === "pdf").length,
          keywords_used: res.keywords || [],
          sources: res.sources,
          ingest_ready: res.ingest_ready,
          auto_ingest: res.auto_ingest,
        });
        onToast(
          `EN/HI/MR discovery: ${res.count} sources` +
            (res.auto_ingest ? ` · ingest ${res.auto_ingest.started}` : ""),
          "ok"
        );
        if (res.auto_ingest?.started) onIngestStarted();
      } else {
        const res = await api.discoverOnline({
          query,
          categories: cats,
          books_bias: books,
          pdf_only: pdfOnly,
          check_access: checkAccess,
          max_results: 40,
          max_keywords: 6,
          auto_ingest: autoIngest,
          auto_ingest_limit: 8,
        });
        setExpanded(null);
        setResult(res);
        onToast(
          `Found ${res.count} sources · allowed ${res.allowed_count} · reachable ${res.reachable_count} · PDFs ${res.pdf_count}` +
            (res.auto_ingest
              ? ` · ingest started ${res.auto_ingest.started}`
              : ""),
          "ok"
        );
        if (res.auto_ingest?.started) onIngestStarted();
      }
    } catch (e) {
      onToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setBusy(false);
    }
  };

  const ingestReady = async () => {
    if (!result?.ingest_ready?.length) {
      onToast("No ingest-ready sources yet — run discovery first", "bad");
      return;
    }
    setBusy(true);
    try {
      const kws = query
        .split(/[,;]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.discoverKeywords({
        keywords: kws.length ? kws : [query],
        languages: langs.length ? langs : ["en", "hi", "mr"],
        max_results: 40,
        check_access: checkAccess,
        auto_ingest: true,
        auto_ingest_limit: 8,
      });
      setResult({
        count: res.count,
        allowed_count: res.count,
        reachable_count: 0,
        pdf_count: res.sources.filter((s) => s.source_type === "pdf").length,
        keywords_used: res.keywords || [],
        sources: res.sources,
        ingest_ready: res.ingest_ready,
        auto_ingest: res.auto_ingest,
      });
      onToast(`Started ingest for ${res.auto_ingest?.started ?? 0} sources`, "ok");
      onIngestStarted();
    } catch (e) {
      onToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid">
      <div className="card">
        <h3>Agri / farmer keyword discovery (online)</h3>
        <p className="hint">
          Searches trusted open services only: Wikipedia, Open Library, Internet
          Archive, Wikimedia Commons PDFs, plus FAO / USDA / ICAR seeds. Filters
          by allow-list and probes access before ingest.
        </p>
        <div className="form-grid">
          <label className="field">
            Free-text query
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {taxonomy.map((c) => (
              <label
                key={c.id}
                className="pill"
                style={{
                  cursor: "pointer",
                  outline: cats.includes(c.id)
                    ? "1px solid var(--accent)"
                    : undefined,
                }}
                title={(c.keywords || []).slice(0, 4).join(", ")}
              >
                <input
                  type="checkbox"
                  checked={cats.includes(c.id)}
                  onChange={() => toggleCat(c.id)}
                />{" "}
                {c.label}
              </label>
            ))}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
            <span className="faint">Languages:</span>
            {(["en", "hi", "mr"] as const).map((L) => (
              <label key={L} className="pill" style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={langs.includes(L)}
                  onChange={() => toggleLang(L)}
                />{" "}
                {L === "en" ? "English" : L === "hi" ? "Hindi हिंदी" : "Marathi मराठी"}
              </label>
            ))}
          </div>
          <div className="form-row" style={{ gap: 16 }}>
            <label>
              <input
                type="checkbox"
                checked={useMultilingual}
                onChange={(e) => setUseMultilingual(e.target.checked)}
              />{" "}
              Multilingual EN/HI/MR mode
            </label>
            <label>
              <input
                type="checkbox"
                checked={books}
                onChange={(e) => setBooks(e.target.checked)}
              />{" "}
              Bias PDF books
            </label>
            <label>
              <input
                type="checkbox"
                checked={pdfOnly}
                onChange={(e) => setPdfOnly(e.target.checked)}
              />{" "}
              PDF only
            </label>
            <label>
              <input
                type="checkbox"
                checked={checkAccess}
                onChange={(e) => setCheckAccess(e.target.checked)}
              />{" "}
              Check access
            </label>
            <label>
              <input
                type="checkbox"
                checked={autoIngest}
                onChange={(e) => setAutoIngest(e.target.checked)}
              />{" "}
              Auto-ingest ready
            </label>
          </div>
          {expanded ? (
            <p className="hint">
              Expanded: EN [{(expanded.en || []).slice(0, 4).join(", ")}] · HI [
              {(expanded.hi || []).slice(0, 3).join(", ")}] · MR [
              {(expanded.mr || []).slice(0, 3).join(", ")}]
            </p>
          ) : null}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn primary" disabled={busy} onClick={run}>
              {busy ? "Discovering…" : "⌕ Discover online"}
            </button>
            <button className="btn" disabled={busy} onClick={ingestReady}>
              Ingest ready sources
            </button>
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Discovery services</h3>
          {!servicesMeta.length ? (
            <Empty>Load services from API…</Empty>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Kind</th>
                    <th>Formats</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {servicesMeta.map((s) => (
                    <tr key={String(s.id)}>
                      <td>
                        <strong>{String(s.name)}</strong>
                        <div className="faint">{String(s.agri_focus || "")}</div>
                      </td>
                      <td className="mono">{String(s.kind)}</td>
                      <td className="mono">
                        {Array.isArray(s.formats)
                          ? (s.formats as string[]).join(", ")
                          : "—"}
                      </td>
                      <td>
                        <Pill status={s.status === "online" ? "curated" : "processing"}>
                          {String(s.status)}
                        </Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <h3>Last discovery KPIs</h3>
          {!result ? (
            <Empty>Run discovery to see keywords + counts.</Empty>
          ) : (
            <>
              <div className="detail-grid">
                <div>
                  <div className="k">Found</div>
                  <div className="v">{result.count}</div>
                </div>
                <div>
                  <div className="k">Allow-listed</div>
                  <div className="v">{result.allowed_count}</div>
                </div>
                <div>
                  <div className="k">Reachable</div>
                  <div className="v">{result.reachable_count}</div>
                </div>
                <div>
                  <div className="k">PDFs</div>
                  <div className="v">{result.pdf_count}</div>
                </div>
              </div>
              <p className="hint" style={{ marginTop: 12 }}>
                Keywords:{" "}
                <span className="mono">{result.keywords_used?.join(" · ")}</span>
              </p>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Discovered sources</h3>
        {!result?.sources?.length ? (
          <Empty>No hits yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Lang</th>
                  <th>Type</th>
                  <th>Provider</th>
                  <th>Trust</th>
                  <th>Allowed</th>
                  <th>Access</th>
                  <th>License</th>
                </tr>
              </thead>
              <tbody>
                {result.sources.map((s, i) => {
                  const access = (s.access || {}) as Record<string, unknown>;
                  const accessStatus = String(s.access_status || "");
                  return (
                    <tr key={`${String(s.source_url)}-${i}`}>
                      <td>
                        <div>{String(s.title || "—")}</div>
                        <div className="mono faint" style={{ maxWidth: 360 }}>
                          {String(s.source_url || "").slice(0, 72)}
                          {String(s.source_url || "").length > 72 ? "…" : ""}
                        </div>
                      </td>
                      <td className="mono">{String(s.language || "—")}</td>
                      <td className="mono">{String(s.source_type)}</td>
                      <td>
                        {String(s.provider || "—")}
                        <div className="faint mono">
                          {String(s.service || "")}
                        </div>
                      </td>
                      <td className="mono">
                        {s.trust_score != null ? String(s.trust_score) : "—"}
                      </td>
                      <td>
                        <Pill status={s.allowed !== false ? "curated" : "failed"}>
                          {s.allowed === false ? "no" : "yes"}
                        </Pill>
                      </td>
                      <td>
                        {access.reachable != null ? (
                          <Pill
                            status={access.reachable ? "curated" : "quarantine"}
                          >
                            {access.reachable
                              ? `HTTP ${access.status_code ?? "ok"}`
                              : "down"}
                          </Pill>
                        ) : accessStatus ? (
                          <span className="mono faint">{accessStatus}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="mono">{String(s.license)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function IngestView({
  onDone,
  onToast,
}: {
  onDone: () => void;
  onToast: (m: string, t?: "ok" | "bad") => void;
}) {
  const [sourceUrl, setSourceUrl] = useState(
    "https://en.wikipedia.org/wiki/Soil_health"
  );
  const [sourceType, setSourceType] = useState<SourceType>("wikipedia");
  const [license, setLicense] = useState("cc-by-sa");
  const [mode, setMode] = useState<IngestMode>("local");
  const [acqMode, setAcqMode] = useState<"demo" | "real">("real");
  const [content, setContent] = useState(
    "ICAR soil health and crop pest IPM advisory for farmers: fertilizer, irrigation, cotton bollworm monitoring."
  );
  const [useInline, setUseInline] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [last, setLast] = useState<Record<string, unknown> | null>(null);
  const [discover, setDiscover] = useState<
    Array<Record<string, unknown>> | null
  >(null);

  const submit = async () => {
    setSubmitting(true);
    try {
      if (acqMode === "real" && useInline) {
        throw new Error("REAL mode forbids inline mock content — uncheck Use inline");
      }
      const res = await api.ingest({
        source_url: sourceUrl,
        source_type: sourceType,
        license,
        mode,
        acq_mode: acqMode,
        content: acqMode === "demo" && useInline ? content : null,
        workflow: "IngestionWorkflow",
        async_run: true,
      });
      setLast(res);
      onToast(
        `${acqMode.toUpperCase()} ${String(res.status)} · run ${String(res.run_id)} · job ${String(res.job_id)}`,
        "ok"
      );
      onDone();
    } catch (e) {
      onToast(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setSubmitting(false);
    }
  };

  const runDiscover = async () => {
    try {
      const res = await api.discover({
        candidates: [
          { source_url: sourceUrl, source_type: sourceType, license },
          {
            source_url: "https://evil.example.net/x",
            source_type: "web",
            license: "unknown",
          },
          {
            source_url: "https://en.wikipedia.org/wiki/Crop_rotation",
            source_type: "wikipedia",
            license: "cc-by-sa",
          },
        ],
      });
      setDiscover(res.sources);
      onToast(`Discovery: ${res.count} candidates filtered`, "ok");
    } catch (e) {
      onToast(e instanceof Error ? e.message : String(e), "bad");
    }
  };

  return (
    <div className="grid two">
      <div className="card">
        <h3>Submit source · full pipeline</h3>
        <p className="hint">
          Stages 1–13: allow-list → license/robots → download → normalize → PII →
          toxicity → relevance → dedup → quality → provenance → raw/curated →
          quarantine.
        </p>
        <div className="form-grid">
          <label className="field">
            Source URL
            <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          </label>
          <div className="form-row">
            <label className="field">
              Acquisition mode
              <select
                value={acqMode}
                onChange={(e) => {
                  const m = e.target.value as "demo" | "real";
                  setAcqMode(m);
                  if (m === "real") setUseInline(false);
                }}
              >
                <option value="real">REAL (trusted live only)</option>
                <option value="demo">DEMO (example/inline OK)</option>
              </select>
            </label>
            <label className="field">
              Source type
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as SourceType)}
              >
                {SOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              License
              <select value={license} onChange={(e) => setLicense(e.target.value)}>
                {LICENSES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-row">
            <label className="field">
              Mode
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as IngestMode)}
              >
                <option value="local">local (offline pipeline)</option>
                <option value="auto">auto (Temporal → local)</option>
                <option value="temporal">temporal only</option>
              </select>
            </label>
            <label className="field" style={{ alignContent: "end" }}>
              <span>
                <input
                  type="checkbox"
                  checked={useInline}
                  disabled={acqMode === "real"}
                  onChange={(e) => setUseInline(e.target.checked)}
                />{" "}
                Use inline content (DEMO only)
              </span>
            </label>
          </div>
          {useInline ? (
            <label className="field">
              Inline content
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
            </label>
          ) : null}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn primary" disabled={submitting} onClick={submit}>
              {submitting ? "Running pipeline…" : "Run Ingest"}
            </button>
            <button className="btn" onClick={runDiscover}>
              Stage 1 · Discover allow-list
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Last result</h3>
        {!last ? (
          <Empty>Submit a source to see stage progress and URIs.</Empty>
        ) : (
          <>
            <div className="detail-grid" style={{ marginBottom: 12 }}>
              <div>
                <div className="k">Job</div>
                <div className="v mono">{String(last.job_id)}</div>
              </div>
              <div>
                <div className="k">Status</div>
                <div className="v">
                  <Pill status={String(last.status)}>{String(last.status)}</Pill>
                </div>
              </div>
              <div>
                <div className="k">Progress</div>
                <div className="v mono">
                  {String(
                    (last.progress as { percent?: number } | undefined)?.percent ??
                      "—"
                  )}
                  %
                </div>
              </div>
              <div>
                <div className="k">Manifest</div>
                <div className="v mono">{String(last.manifest_id || "—")}</div>
              </div>
            </div>
            {(last.progress as { checklist?: Array<{ stage: string; done: boolean }> })
              ?.checklist ? (
              <div className="stage-list">
                {(
                  last.progress as {
                    checklist: Array<{ stage: string; done: boolean }>;
                  }
                ).checklist.map((s) => (
                  <div
                    key={s.stage}
                    className={`stage-item ${s.done ? "done" : ""}`}
                  >
                    <span className="dot" />
                    <span>{s.stage}</span>
                    <span className="faint">{s.done ? "done" : "pending"}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {last.error ? (
              <div className="alert warn" style={{ marginTop: 12 }}>
                {String(last.error)}
              </div>
            ) : null}
          </>
        )}

        {discover ? (
          <>
            <h3 style={{ marginTop: 18 }}>Discovery results</h3>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>URL</th>
                    <th>Type</th>
                    <th>Allowed</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {discover.map((s, i) => (
                    <tr key={i}>
                      <td className="mono">{String(s.source_url)}</td>
                      <td>{String(s.source_type)}</td>
                      <td>
                        <Pill status={s.allowed ? "curated" : "failed"}>
                          {s.allowed ? "yes" : "no"}
                        </Pill>
                      </td>
                      <td className="faint">{String(s.reason || "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function MonitorView({
  jobs,
  selected,
  onSelect,
  onRefresh,
  activeRunId,
  onToast,
}: {
  jobs: JobRecord[];
  selected: JobRecord | null;
  onSelect: (j: JobRecord | null) => void;
  onRefresh: () => void;
  activeRunId?: string | null;
  onToast?: (m: string, t?: "ok" | "bad") => void;
}) {
  const [failReport, setFailReport] = useState<Record<string, unknown> | null>(
    null
  );
  const [runMeta, setRunMeta] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!activeRunId) {
      setFailReport(null);
      setRunMeta(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [detail, report] = await Promise.all([
          api.getRun(activeRunId),
          api.runReport(activeRunId),
        ]);
        if (cancelled) return;
        setRunMeta({
          outcome: detail.outcome,
          partial: detail.partial,
          jobs_by_status: detail.jobs_by_status,
          paths: (detail.run as { paths?: unknown })?.paths,
        });
        setFailReport(report as unknown as Record<string, unknown>);
      } catch {
        /* offline */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeRunId]);
  const job = selected || jobs[0] || null;
  const checklist = job?.progress?.checklist || [];

  const failSummary = (failReport?.summary || {}) as Record<string, unknown>;
  const failClasses = (failSummary.failure_classes || {}) as Record<
    string,
    number
  >;

  return (
    <div className="grid">
      {activeRunId ? (
        <div className="card">
          <h3>
            Run outcome
            <Pill
              status={
                runMeta?.outcome === "success"
                  ? "curated"
                  : runMeta?.outcome === "partial"
                    ? "processing"
                    : runMeta?.outcome === "failed"
                      ? "failed"
                      : "queued"
              }
            >
              {String(runMeta?.outcome || "…")}
            </Pill>
          </h3>
          <p className="hint mono">runId: {activeRunId}</p>
          {runMeta?.jobs_by_status ? (
            <div className="detail-grid" style={{ marginBottom: 10 }}>
              {Object.entries(
                runMeta.jobs_by_status as Record<string, number>
              ).map(([k, v]) => (
                <div key={k}>
                  <div className="k">{k}</div>
                  <div className="v">{v}</div>
                </div>
              ))}
            </div>
          ) : null}
          {failReport ? (
            <>
              <p className="hint">
                Failure classes:{" "}
                {Object.keys(failClasses).length
                  ? Object.entries(failClasses)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(" · ")
                  : "none"}
              </p>
              <button
                className="btn"
                onClick={() => {
                  const blob = new Blob(
                    [JSON.stringify(failReport, null, 2)],
                    { type: "application/json" }
                  );
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${String(failReport.report_id || "run-report")}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  onToast?.("Failure report downloaded", "ok");
                }}
              >
                Download failure report
              </button>
              {(failReport.recommendations as string[] | undefined)?.length ? (
                <ul className="hint" style={{ marginTop: 10 }}>
                  {(failReport.recommendations as string[]).map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : null}
              {(failReport.failures as Array<Record<string, unknown>> | undefined)
                ?.length ? (
                <div className="table-wrap" style={{ marginTop: 12 }}>
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Job</th>
                        <th>Class</th>
                        <th>Stage</th>
                        <th>Error</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        failReport.failures as Array<Record<string, unknown>>
                      ).map((f) => (
                        <tr
                          key={String(f.job_id)}
                          style={{ cursor: "pointer" }}
                          onClick={() => {
                            const match = jobs.find(
                              (j) => j.job_id === f.job_id
                            );
                            if (match) onSelect(match);
                          }}
                        >
                          <td className="mono">{String(f.job_id)}</td>
                          <td>
                            <Pill status="failed">
                              {String(f.failure_class || "—")}
                            </Pill>
                          </td>
                          <td className="mono">
                            {String(f.failed_stage || "—")}
                          </td>
                          <td className="faint">
                            {String(f.error || "").slice(0, 80)}
                          </td>
                          <td className="mono faint">
                            {String(f.source_url || "").slice(0, 48)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </>
          ) : (
            <Empty>Loading run failure report…</Empty>
          )}
        </div>
      ) : null}

      <div className="grid two">
        <div className="card">
          <h3>
            Job stream
            <button className="btn ghost" onClick={onRefresh}>
              Refresh
            </button>
          </h3>
          <JobsTable
            jobs={jobs}
            onSelect={(j) => {
              onSelect(j);
            }}
          />
        </div>
        <div className="card">
          <h3>Job detail · stage %</h3>
          {!job ? (
            <Empty>Select a job.</Empty>
          ) : (
            <>
              <div style={{ marginBottom: 10 }}>
                <Pill status={job.status}>{job.status}</Pill>{" "}
                <span className="mono">{job.job_id}</span>
                {job.run_id ? (
                  <div className="faint mono">run: {job.run_id}</div>
                ) : null}
              </div>
              {(job.qa_summary?.error || job.error) && (
                <div className="alert bad" style={{ marginBottom: 10 }}>
                  <strong>
                    {String(
                      job.failure_class ||
                        job.qa_summary?.failure_class ||
                        "error"
                    )}
                  </strong>
                  : {String(job.qa_summary?.error || job.error)}
                </div>
              )}
              <div style={{ marginBottom: 8 }} className="mono">
                {(() => {
                  let p = job.progress?.percent ?? 0;
                  if (
                    (job.status === "failed" || job.status === "quarantine") &&
                    p >= 100
                  ) {
                    const done = job.progress?.completed_count ?? 0;
                    const total = job.progress?.total_stages ?? 16;
                    p = Math.min(99, Math.round((100 * done) / total) || 12);
                  }
                  const st =
                    job.progress?.failed_stage ||
                    job.progress?.current_stage ||
                    "—";
                  return `${p}% · stage ${st}${
                    job.progress?.partial || job.status === "failed"
                      ? " · partial"
                      : ""
                  }`;
                })()}
              </div>
              <ProgressBar
                percent={(() => {
                  let p = job.progress?.percent ?? 0;
                  if (
                    (job.status === "failed" || job.status === "quarantine") &&
                    p >= 100
                  ) {
                    const done = job.progress?.completed_count ?? 0;
                    const total = job.progress?.total_stages ?? 16;
                    p = Math.min(99, Math.round((100 * done) / total) || 12);
                  }
                  return p;
                })()}
                tone={
                  job.status === "failed"
                    ? "bad"
                    : job.status === "quarantine"
                      ? "warn"
                      : ""
                }
              />
              <div className="stage-list" style={{ marginTop: 14 }}>
                {checklist.map((s) => (
                  <div
                    key={s.stage}
                    className={`stage-item ${s.done ? "done" : ""} ${(s as { failed?: boolean }).failed ? "failed" : ""}`}
                  >
                    <span className="dot" />
                    <span>{s.stage}</span>
                    <span className="faint">
                      {(s as { failed?: boolean }).failed
                        ? "✕"
                        : s.done
                          ? "✓"
                          : "·"}
                    </span>
                  </div>
                ))}
              </div>
              <h3 style={{ marginTop: 16 }}>QA summary</h3>
              <pre
                className="mono"
                style={{
                  whiteSpace: "pre-wrap",
                  background: "rgba(0,0,0,.25)",
                  padding: 12,
                  borderRadius: 10,
                  fontSize: 11,
                  maxHeight: 220,
                  overflow: "auto",
                }}
              >
                {JSON.stringify(job.qa_summary || job.result, null, 2)}
              </pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CorpusView({
  runId,
  acqMode,
}: {
  runId?: string | null;
  acqMode?: "demo" | "real";
}) {
  const fetch = useCallback(
    () =>
      api.corpus(150, {
        run_id: runId || undefined,
        acq_mode: acqMode,
      }),
    [runId, acqMode]
  );
  const { data, error, loading, refresh } = usePolling(fetch, 5000, true);

  if (loading && !data) return <Empty>Loading corpus…</Empty>;
  if (error) return <div className="alert bad">{error}</div>;
  if (!data) return <Empty>No corpus data.</Empty>;

  const s = data.summary;
  return (
    <div className="grid">
      {runId ? (
        <div className="alert" style={{ marginBottom: 8 }}>
          Showing <strong>partial corpus for run</strong>{" "}
          <span className="mono">{runId}</span> (jobs that curated successfully).
        </div>
      ) : (
        <div className="hint">
          Tip: run Real sources first, then open corpus with an active runId for
          partial data.
        </div>
      )}
      <div className="grid kpis">
        <KpiCard label="Status" value={String(data.status)} accent="var(--ok)" />
        <KpiCard label="Documents" value={String(s.documents)} />
        <KpiCard label="Chunks" value={String(s.chunks)} />
        <KpiCard label="Images" value={String(s.images)} />
        <KpiCard label="Total records" value={String(s.total_records)} />
        <KpiCard
          label="Size"
          value={String(s.size_human)}
          meta={`${s.size_bytes} bytes`}
        />
      </div>
      <div className="card">
        <h3>
          Ready corpus documents
          <button className="btn ghost" onClick={refresh}>
            Refresh
          </button>
        </h3>
        <p className="hint">
          Curated, quality-scored, PII-redacted docs ready for indexing / training.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Document</th>
                <th>Quality</th>
                <th>Lang</th>
                <th>Size</th>
                <th>License</th>
                <th>Preview</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((d) => (
                <tr key={String(d.document_id)}>
                  <td>
                    <div className="mono">{String(d.document_id).slice(0, 12)}</div>
                    <div className="faint mono">
                      {String(d.source_url || "").slice(0, 40)}
                    </div>
                  </td>
                  <td className="mono">
                    {d.quality_score != null
                      ? Number(d.quality_score).toFixed(2)
                      : "—"}
                  </td>
                  <td>{String(d.language || "—")}</td>
                  <td className="mono">{humanBytes(Number(d.size_bytes || 0))}</td>
                  <td>{String(d.license || "—")}</td>
                  <td className="muted">{String(d.preview || "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="grid two">
        <div className="card">
          <h3>Chunks sample</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Doc</th>
                  <th>Idx</th>
                  <th>Chars</th>
                  <th>Preview</th>
                </tr>
              </thead>
              <tbody>
                {data.chunks_sample.map((c, i) => (
                  <tr key={i}>
                    <td className="mono">
                      {String(c.document_id || "").slice(0, 10)}
                    </td>
                    <td>{String(c.chunk_index)}</td>
                    <td>{String(c.chars)}</td>
                    <td className="muted">{String(c.preview || "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h3>Manifests</h3>
          {!data.manifests.length ? (
            <Empty>No manifests yet.</Empty>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Records</th>
                    <th>Checksum</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.manifests.map((m) => (
                    <tr key={String(m.manifest_id)}>
                      <td className="mono">{String(m.manifest_id)}</td>
                      <td>{String(m.record_count)}</td>
                      <td className="mono">
                        {String(m.checksum || "").slice(0, 18)}…
                      </td>
                      <td className="muted">{String(m.notes || "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function QualityView() {
  const fetch = useCallback(() => api.quality(200), []);
  const { data, error, loading } = usePolling(fetch, 5000, true);
  if (loading && !data) return <Empty>Loading quality…</Empty>;
  if (error) return <div className="alert bad">{error}</div>;
  if (!data) return <Empty>No quality data.</Empty>;

  return (
    <div className="grid">
      <div className="grid kpis">
        <KpiCard
          label="Avg quality"
          value={
            data.avg_quality != null ? data.avg_quality.toFixed(3) : "—"
          }
          accent="var(--info)"
        />
        <KpiCard label="Scored docs" value={String(data.count)} />
        <KpiCard label="High ≥0.75" value={String(data.tiers.high || 0)} accent="var(--ok)" />
        <KpiCard
          label="Medium"
          value={String(data.tiers.medium || 0)}
          accent="var(--warn)"
        />
        <KpiCard label="Low" value={String(data.tiers.low || 0)} accent="var(--bad)" />
      </div>
      <div className="card">
        <h3>Quality ledger</h3>
        <p className="hint">
          Transparency for QA: every curated document quality score, relevance,
          PII, toxicity.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Doc</th>
                <th>Tier</th>
                <th>Quality</th>
                <th>Relevance</th>
                <th>Lang</th>
                <th>PII</th>
                <th>Preview</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((r) => (
                <tr key={String(r.document_id)}>
                  <td className="mono">
                    {String(r.document_id || "").slice(0, 12)}
                  </td>
                  <td>
                    <Pill
                      status={
                        r.tier === "high"
                          ? "curated"
                          : r.tier === "low"
                            ? "failed"
                            : "quarantine"
                      }
                    >
                      {String(r.tier)}
                    </Pill>
                  </td>
                  <td className="mono">
                    {r.quality_score != null
                      ? Number(r.quality_score).toFixed(3)
                      : "—"}
                  </td>
                  <td className="mono">
                    {r.relevance_score != null
                      ? Number(r.relevance_score).toFixed(2)
                      : "—"}
                  </td>
                  <td>{String(r.language || "—")}</td>
                  <td>{r.pii_redacted ? "redacted" : "—"}</td>
                  <td className="muted">{String(r.preview || "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function QuarantineView() {
  const fetch = useCallback(() => api.quarantine(200), []);
  const { data, error, loading } = usePolling(fetch, 5000, true);
  if (loading && !data) return <Empty>Loading quarantine…</Empty>;
  if (error) return <div className="alert bad">{error}</div>;
  if (!data) return <Empty>No quarantine data.</Empty>;

  return (
    <div className="grid">
      <div className="grid kpis">
        <KpiCard label="Quarantined" value={String(data.count)} accent="var(--warn)" />
        <KpiCard
          label="Duplicates in Q"
          value={String(data.duplicate_count)}
          accent="var(--purple)"
        />
      </div>
      <div className="grid two">
        <div className="card">
          <h3>Reason breakdown</h3>
          <BarChart data={data.reasons} color="var(--warn)" />
        </div>
        <div className="card">
          <h3>What gets quarantined?</h3>
          <ul className="muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
            <li>Not allow-listed sources</li>
            <li>Blocked licenses / robots</li>
            <li>Toxicity / safety filter</li>
            <li>Low agriculture relevance</li>
            <li>Exact + MinHash near-duplicates</li>
            <li>Low quality score</li>
            <li>Audio awaiting ASR</li>
          </ul>
        </div>
      </div>
      <div className="card">
        <h3>Quarantine records</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Job</th>
                <th>Reason</th>
                <th>Dup?</th>
                <th>Source</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{String(r.job_id || "").slice(0, 12)}</td>
                  <td>
                    <Pill status="quarantine">{String(r.reason)}</Pill>
                  </td>
                  <td>{r.is_duplicate ? "yes" : "no"}</td>
                  <td className="mono">
                    {String(r.source_url || "").slice(0, 48)}
                  </td>
                  <td className="faint">
                    {r.quarantined_at
                      ? new Date(String(r.quarantined_at)).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function DuplicatesView() {
  const fetch = useCallback(() => api.duplicates(200), []);
  const { data, error, loading } = usePolling(fetch, 5000, true);
  if (loading && !data) return <Empty>Loading duplicates…</Empty>;
  if (error) return <div className="alert bad">{error}</div>;
  if (!data) return <Empty>No duplicates.</Empty>;

  return (
    <div className="card">
      <h3>
        Deduplication ledger{" "}
        <Pill status="quarantine">{data.count} duplicates</Pill>
      </h3>
      <p className="hint">
        Exact hash + fingerprint + MinHash near-duplicate quarantine rows
        (stage 8).
      </p>
      {!data.records.length ? (
        <Empty>
          No duplicates yet. Run demo batch twice or re-ingest the same content.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Job</th>
                <th>Reason</th>
                <th>Duplicate of</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{String(r.job_id)}</td>
                  <td>{String(r.reason)}</td>
                  <td className="mono">
                    {String(r.duplicate_of || "—").slice(0, 24)}
                  </td>
                  <td className="mono">{String(r.source_url || "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ReportView({
  activeRunId,
  onToast,
}: {
  activeRunId?: string | null;
  onToast?: (m: string, t?: "ok" | "bad") => void;
}) {
  const [report, setReport] = useState<QaReport | null>(null);
  const [failReport, setFailReport] = useState<Record<string, unknown> | null>(
    null
  );
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      setReport(await api.report(true));
      if (activeRunId) {
        setFailReport(
          (await api.runReport(activeRunId)) as unknown as Record<
            string,
            unknown
          >
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${report.report_id}.json`;
    a.click();
  };

  const downloadFail = () => {
    if (!failReport) return;
    const blob = new Blob([JSON.stringify(failReport, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${String(failReport.report_id || "failure-report")}.json`;
    a.click();
    onToast?.("Failure report exported", "ok");
  };

  return (
    <div className="grid">
      {activeRunId ? (
        <div className="card">
          <h3>
            Run failure / partial report
            <span style={{ display: "flex", gap: 8 }}>
              <button className="btn primary" onClick={load} disabled={loading}>
                {loading ? "Generating…" : "Generate run report"}
              </button>
              <button className="btn" onClick={downloadFail} disabled={!failReport}>
                Export failure JSON
              </button>
            </span>
          </h3>
          <p className="hint mono">runId: {activeRunId}</p>
          {failReport ? (
            <>
              <div className="detail-grid">
                <div>
                  <div className="k">Outcome</div>
                  <div className="v">{String(failReport.outcome)}</div>
                </div>
                <div>
                  <div className="k">Success</div>
                  <div className="v">
                    {String(
                      (failReport.summary as Record<string, unknown>)
                        ?.success_count ?? "—"
                    )}
                  </div>
                </div>
                <div>
                  <div className="k">Failed/quarantine</div>
                  <div className="v">
                    {String(
                      (failReport.summary as Record<string, unknown>)
                        ?.failed_or_quarantine ?? "—"
                    )}
                  </div>
                </div>
                <div>
                  <div className="k">Partial corpus docs</div>
                  <div className="v">
                    {String(
                      (
                        (failReport.partial_corpus as Record<string, unknown>)
                          ?.summary as Record<string, unknown> | undefined
                      )?.documents ?? "—"
                    )}
                  </div>
                </div>
              </div>
              {failReport.saved_path ? (
                <p className="hint mono">Saved: {String(failReport.saved_path)}</p>
              ) : null}
            </>
          ) : (
            <Empty>Generate to load failure tracking report for this run.</Empty>
          )}
        </div>
      ) : null}
      <div className="card">
        <h3>
          QA audit report
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" onClick={load} disabled={loading}>
              {loading ? "Generating…" : "Generate report"}
            </button>
            <button className="btn" onClick={download} disabled={!report}>
              Export JSON
            </button>
          </span>
        </h3>
        <p className="hint">
          Checklist score, KPIs, recommendations, and sample rows for auditors.
        </p>
        {err ? <div className="alert bad">{err}</div> : null}
        {!report ? (
          <Empty>Generate a report after seeding demo or ingest jobs.</Empty>
        ) : (
          <div className="grid two">
            <div style={{ textAlign: "center" }}>
              <ScoreRing pct={report.qa_score_pct} />
              <div className="muted">QA score · {report.report_id}</div>
              <div className="faint" style={{ marginTop: 6 }}>
                {new Date(report.generated_at).toLocaleString()}
              </div>
            </div>
            <div>
              <h3>Recommendations</h3>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
                {report.recommendations.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
      {report ? (
        <div className="card">
          <h3>Checklist</h3>
          <div className="checklist">
            {report.qa_checklist.map((c) => (
              <div
                key={c.id}
                className={`check-item ${c.pass ? "pass" : "fail"}`}
              >
                <span>{c.pass ? "✓" : "✕"}</span>
                <div>
                  <div>{c.label}</div>
                  {c.info ? <div className="faint mono">{c.info}</div> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LakehouseView({ tables }: { tables?: Record<string, number> }) {
  const names = useMemo(
    () =>
      tables
        ? Object.keys(tables)
        : [
            "raw.documents",
            "curated.documents",
            "curated.chunks",
            "curated.images",
            "quarantine.records",
            "manifests.datasets",
            "manifests.models",
            "telemetry.events",
          ],
    [tables]
  );
  const [active, setActive] = useState(names[0]);
  const [rows, setRows] = useState<unknown[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = async (name: string) => {
    setActive(name);
    setErr(null);
    try {
      const res = await api.table(name, 50);
      setRows(res.rows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  };

  useEffect(() => {
    void load(active);
    // initial table load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid">
      <div className="grid kpis">
        {names.map((n) => (
          <div
            key={n}
            className="card kpi"
            style={{
              cursor: "pointer",
              outline: active === n ? "1px solid var(--accent)" : undefined,
            }}
            onClick={() => load(n)}
          >
            <div className="label">{n}</div>
            <div className="value">{tables?.[n] ?? "·"}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>
          Table · <span className="mono">{active}</span>
        </h3>
        {err ? <div className="alert bad">{err}</div> : null}
        {!rows.length ? (
          <Empty>No rows (or empty table).</Empty>
        ) : (
          <pre
            className="mono"
            style={{
              maxHeight: 480,
              overflow: "auto",
              fontSize: 11,
              background: "rgba(0,0,0,.25)",
              padding: 12,
              borderRadius: 10,
            }}
          >
            {JSON.stringify(rows, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
