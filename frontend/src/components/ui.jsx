/**
 * Shared presentational primitives.
 *
 * Colour carries meaning and nothing else: red = critical/high fatal potential,
 * amber = medium, green = low/controls held, navy = neutral chrome. Nothing is
 * coloured for decoration.
 */

import { AlertTriangle, Info, Loader2, ShieldCheck } from "lucide-react";

/* ---------------------------------------------------------------- states */

export function Loading({ label = "Analysing..." }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slate-500">
      <Loader2 className="w-4 h-4 animate-spin" />
      <span className="text-[13px]">{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="card p-6 border-danger-200 bg-danger-50">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-danger-600 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-semibold text-danger-700 text-[13px]">Could not load this view</p>
          <p className="text-[12.5px] text-danger-700/90 mt-1 break-words">{String(error)}</p>
          {onRetry && (
            <button onClick={onRetry} className="btn-ghost mt-3">
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Empty({ title = "Nothing to show", hint }) {
  return (
    <div className="py-14 text-center">
      <Info className="w-5 h-5 text-slate-300 mx-auto mb-2" />
      <p className="text-[13px] font-medium text-slate-600">{title}</p>
      {hint && <p className="text-[12px] text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- badges */

const RISK_STYLES = {
  Critical: "bg-danger-50 text-danger-700 border-danger-200",
  High: "bg-warn-50 text-warn-700 border-warn-200",
  Medium: "bg-info-50 text-info-700 border-info-200",
  Low: "bg-safe-50 text-safe-700 border-safe-200",
  Unranked: "bg-slate-100 text-slate-500 border-slate-200",
};

export function RiskBadge({ level }) {
  return (
    <span className={`chip ${RISK_STYLES[level] || RISK_STYLES.Unranked}`}>
      {level === "Critical" && <AlertTriangle className="w-3 h-3" />}
      {level}
    </span>
  );
}

export function SifBadge({ isSif }) {
  return isSif ? (
    <span className="chip bg-danger-50 text-danger-700 border-danger-200">
      <AlertTriangle className="w-3 h-3" />
      SIF-Potential
    </span>
  ) : (
    <span className="chip bg-safe-50 text-safe-700 border-safe-200">
      <ShieldCheck className="w-3 h-3" />
      Non-SIF
    </span>
  );
}

export function StatusChip({ status }) {
  const styles = {
    "Pending Review": "bg-slate-100 text-slate-600 border-slate-200",
    "Under Review": "bg-info-50 text-info-700 border-info-200",
    Reviewed: "bg-safe-50 text-safe-700 border-safe-200",
  };
  return <span className={`chip ${styles[status] || styles["Pending Review"]}`}>{status}</span>;
}

/* --------------------------------------------------------------- metrics */

export function ConfidenceBar({ value, showLabel = true }) {
  const pct = Math.round((value || 0) * 100);
  const tone = pct >= 70 ? "bg-danger-500" : pct >= 50 ? "bg-warn-500" : "bg-slate-400";
  return (
    <div className="flex items-center gap-2 min-w-[92px]">
      <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {showLabel && <span className="text-[11.5px] tabular-nums text-slate-600 w-8">{pct}%</span>}
    </div>
  );
}

export function KpiCard({ icon: Icon, label, value, sub, tone = "neutral", hint }) {
  const tones = {
    neutral: "text-navy-800 bg-navy-50",
    danger: "text-danger-600 bg-danger-50",
    warn: "text-warn-600 bg-warn-50",
    safe: "text-safe-600 bg-safe-50",
    info: "text-info-600 bg-info-50",
  };
  return (
    <div className="card p-3.5" title={hint}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide truncate">
            {label}
          </p>
          <p className="text-[22px] font-bold text-navy-900 mt-1 tabular-nums leading-none">
            {value}
          </p>
          {sub && <p className="text-[11.5px] text-slate-500 mt-1.5 truncate">{sub}</p>}
        </div>
        {Icon && (
          <div className={`p-1.5 rounded-md shrink-0 ${tones[tone]}`}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- disclaimers */

export function DemoBanner({ banner }) {
  if (!banner) return null;
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-warn-50 border border-warn-200">
      <AlertTriangle className="w-3.5 h-3.5 text-warn-600 shrink-0" />
      <span className="text-[11.5px] font-semibold text-warn-700 tracking-wide">{banner}</span>
    </div>
  );
}

export function DecisionSupportNotice({ compact = false }) {
  return (
    <div
      className={`flex items-start gap-2 rounded-md bg-info-50 border border-info-200 ${
        compact ? "px-3 py-2" : "px-4 py-3"
      }`}
    >
      <Info className="w-3.5 h-3.5 text-info-600 shrink-0 mt-0.5" />
      <p className="text-[11.5px] text-info-700 leading-snug">
        <strong>AI prioritises. HSE decides.</strong> AI output is a decision-support signal and
        requires qualified HSE verification. It does not predict accidents or replace professional
        judgement.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------- helpers */

export const pct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "-" : `${(v * 100).toFixed(digits)}%`;

export const num = (v) =>
  v === null || v === undefined ? "-" : Number(v).toLocaleString("en-IN");
