import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Gauge,
  MapPin,
  ShieldAlert,
  ShieldCheck,
  Target,
  X,
  XCircle,
} from "lucide-react";

import { ConfidenceBar, RiskBadge, SifBadge, StatusChip, pct } from "./ui";

/**
 * Detailed report analysis.
 *
 * The controlling idea: an HSE professional must be able to audit and overrule
 * every conclusion. So we always show the original narrative verbatim, the
 * evidence snippet behind each barrier judgement, and a written explanation of
 * why a Life-Saving Rule was chosen - never a bare score.
 */
export default function ReportAnalysis({ report: r, onClose }) {
  const failed = (r.barrier_evidence || []).filter((b) => b.status === "FAILED");
  const present = (r.barrier_evidence || []).filter((b) => b.status === "PRESENT");

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-navy-950/40" onClick={onClose}>
      <div
        className="bg-slate-50 w-full max-w-3xl h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ------------------------------------------------------- header */}
        <div className="bg-white border-b border-slate-200 px-5 py-3.5 sticky top-0 z-10">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[12px] text-info-700">{r.report_id}</span>
                <SifBadge isSif={r.is_sif} />
                <RiskBadge level={r.risk_level} />
                <StatusChip status={r.status} />
              </div>
              <div className="flex items-center gap-3 mt-1.5 text-[11.5px] text-slate-500 flex-wrap">
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" />
                  {r.location} / {r.asset}
                </span>
                <span>{r.date || "date unknown"}</span>
                <span>{r.report_type}</span>
              </div>
            </div>
            <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded shrink-0">
              <X className="w-4 h-4 text-slate-500" />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {/* ------------------------------------------ original report */}
          <section className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-slate-400" />
                <h3 className="card-title">Original Report</h3>
              </div>
            </div>
            <div className="p-4">
              <p className="text-[13px] text-navy-900 leading-relaxed whitespace-pre-wrap">
                {r.narrative}
              </p>
            </div>
          </section>

          {/* --------------------------------------------- AI analysis */}
          <section className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 text-slate-400" />
                <h3 className="card-title">AI Analysis</h3>
              </div>
            </div>
            <div className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Metric label="Classification">
                <p
                  className={`text-[15px] font-bold ${
                    r.is_sif ? "text-danger-600" : "text-safe-600"
                  }`}
                >
                  {r.classification}
                </p>
              </Metric>
              <Metric label="Confidence">
                <p className="text-[15px] font-bold text-navy-900 tabular-nums">
                  {pct(r.confidence, 0)}
                </p>
                <ConfidenceBar value={r.confidence} showLabel={false} />
              </Metric>
              <Metric label="Risk Level">
                <RiskBadge level={r.risk_level} />
                <p className="text-[11px] text-slate-500 mt-1 tabular-nums">
                  score {r.risk_score?.toFixed(2)}
                </p>
              </Metric>
            </div>

            {(r.model_probability !== null && r.model_probability !== undefined) && (
              <div className="px-4 pb-4 -mt-1">
                <div className="text-[11.5px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2.5 leading-snug">
                  <strong className="text-navy-700">How this score was reached: </strong>
                  the learned model gave {pct(r.model_probability, 0)} and the knowledge-based
                  energy/barrier rules gave {pct(r.rule_probability, 0)}. These are blended so the
                  system still works on phrasing the rules never anticipated, while remaining
                  explainable when the model is uncertain.
                </div>
              </div>
            )}
          </section>

          {/* ------------------------------------- context: what & where */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <InfoCard label="Activity" value={r.activity} />
            <InfoCard
              label="Hazard"
              value={r.hazard}
              note={r.hazard_is_implied ? "inferred from activity" : null}
            />
            <InfoCard label="Exposure" value={r.exposure} />
          </div>

          {/* ------------------------------------------- precursors */}
          <section className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-slate-400" />
                <div>
                  <h3 className="card-title">Detected Precursors</h3>
                  <p className="card-sub">
                    An exposure that exists combined with a control that did not hold
                  </p>
                </div>
              </div>
            </div>
            <div className="p-4">
              {r.precursors?.length ? (
                <ul className="space-y-1.5">
                  {r.precursors.map((p, i) => (
                    <li key={i} className="flex items-start gap-2 text-[12.5px]">
                      <AlertTriangle className="w-3.5 h-3.5 text-warn-600 shrink-0 mt-0.5" />
                      <span className="text-navy-800">{p}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="flex items-center gap-2 text-[12.5px] text-safe-700">
                  <CheckCircle2 className="w-4 h-4" />
                  No SIF precursor detected. No critical control was found to have failed.
                </div>
              )}
            </div>
          </section>

          {/* ---------------------------------------------- barriers */}
          <section className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-slate-400" />
                <div>
                  <h3 className="card-title">Barrier Analysis</h3>
                  <p className="card-sub">
                    Each control is resolved from context, not keyword presence - the evidence is
                    quoted so you can check it
                  </p>
                </div>
              </div>
            </div>
            <div className="p-4 space-y-3">
              {failed.length === 0 && present.length === 0 && (
                <p className="text-[12.5px] text-slate-400">
                  No critical control was mentioned clearly enough to resolve.
                </p>
              )}

              {failed.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-danger-700 uppercase tracking-wide mb-1.5">
                    Failed or missing ({failed.length})
                  </p>
                  <div className="space-y-1.5">
                    {failed.map((b, i) => (
                      <div key={i} className="rounded-md border border-danger-200 bg-danger-50 p-2.5">
                        <div className="flex items-center gap-1.5">
                          <XCircle className="w-3.5 h-3.5 text-danger-600" />
                          <span className="text-[12.5px] font-semibold text-danger-700">
                            {b.barrier}
                          </span>
                        </div>
                        {b.evidence && (
                          <p className="text-[11.5px] text-danger-700/80 mt-1 italic">
                            &ldquo;{b.evidence}&rdquo;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {present.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-safe-700 uppercase tracking-wide mb-1.5">
                    Controls in place ({present.length})
                  </p>
                  <div className="space-y-1.5">
                    {present.map((b, i) => (
                      <div key={i} className="rounded-md border border-safe-200 bg-safe-50 p-2.5">
                        <div className="flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5 text-safe-600" />
                          <span className="text-[12.5px] font-semibold text-safe-700">
                            {b.barrier}
                          </span>
                        </div>
                        {b.evidence && (
                          <p className="text-[11.5px] text-safe-700/80 mt-1 italic">
                            &ldquo;{b.evidence}&rdquo;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* ------------------------------------------- IOGP mapping */}
          <section className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-slate-400" />
                <h3 className="card-title">IOGP Life-Saving Rule</h3>
              </div>
            </div>
            <div className="p-4">
              <p className="text-[15px] font-bold text-navy-900">{r.iogp_rule_name}</p>
              <p className="text-[12.5px] text-slate-600 mt-2 leading-relaxed">
                {r.iogp_explanation}
              </p>
              {r.iogp_secondary?.length > 0 && (
                <p className="text-[11.5px] text-slate-500 mt-2">
                  Also engaged: {r.iogp_secondary.join(", ")}
                </p>
              )}
            </div>
          </section>

          {/* -------------------------------------------- recommended */}
          <section
            className={`card p-4 ${
              r.needs_review ? "border-warn-200 bg-warn-50" : "border-slate-200"
            }`}
          >
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
              Recommended Action
            </p>
            <p className="text-[13px] font-semibold text-navy-900">
              {r.needs_review || r.is_sif ? "HSE verification required" : "Routine tracking"}
            </p>
            {r.review_reason && (
              <p className="text-[12px] text-warn-700 mt-1">{r.review_reason}</p>
            )}
            <p className="text-[11.5px] text-slate-500 mt-2 leading-snug">
              AI output is a decision-support signal and requires qualified HSE verification. This
              system detects precursor signals - it does not predict accidents.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, children }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
        {label}
      </p>
      {children}
    </div>
  );
}

function InfoCard({ label, value, note }) {
  return (
    <div className="card p-3">
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="text-[12.5px] font-medium text-navy-900 mt-1 leading-snug">{value || "-"}</p>
      {note && <p className="text-[11px] text-slate-400 mt-0.5 italic">{note}</p>}
    </div>
  );
}
