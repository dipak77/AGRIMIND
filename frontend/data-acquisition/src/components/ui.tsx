import type { ReactNode } from "react";
import { statusTone } from "../api/client";

export function Pill({
  status,
  children,
}: {
  status?: string;
  children: ReactNode;
}) {
  const tone = statusTone(status);
  return <span className={`pill ${tone}`}>{children}</span>;
}

export function ProgressBar({
  percent,
  tone,
}: {
  percent: number;
  tone?: "ok" | "warn" | "bad" | "";
}) {
  const p = Math.max(0, Math.min(100, percent || 0));
  return (
    <div className={`progress ${tone || ""}`} title={`${p}%`}>
      <span style={{ width: `${p}%` }} />
    </div>
  );
}

export function KpiCard({
  label,
  value,
  meta,
  accent,
}: {
  label: string;
  value: ReactNode;
  meta?: ReactNode;
  accent?: string;
}) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {meta ? <div className="meta">{meta}</div> : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function BarChart({
  data,
  color,
}: {
  data: Record<string, number>;
  color?: string;
}) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <Empty>No distribution data yet.</Empty>;
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="muted" title={k}>
            {k.length > 18 ? k.slice(0, 16) + "…" : k}
          </span>
          <div className="track">
            <i
              style={{
                width: `${(100 * v) / max}%`,
                background: color || undefined,
              }}
            />
          </div>
          <span className="mono">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function ScoreRing({ pct }: { pct: number }) {
  const p = Math.max(0, Math.min(100, pct));
  return (
    <div className="score-ring" style={{ ["--p" as string]: `${p}%` }}>
      <span>{p.toFixed(0)}%</span>
    </div>
  );
}

export function Toast({
  message,
  tone,
  onClose,
}: {
  message: string;
  tone: "ok" | "bad";
  onClose: () => void;
}) {
  return (
    <div className={`toast ${tone}`} role="status">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <span>{message}</span>
        <button className="btn ghost" onClick={onClose} style={{ padding: "0 4px" }}>
          ✕
        </button>
      </div>
    </div>
  );
}
