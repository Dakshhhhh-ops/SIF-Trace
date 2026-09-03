import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckSquare, Info, Users } from "lucide-react";

import api from "../api";
import {
  ConfidenceBar,
  DecisionSupportNotice,
  Empty,
  ErrorState,
  Loading,
  RiskBadge,
  num,
  pct,
} from "../components/ui";

export default function Validation() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null);
    Promise.all([api.validation(), api.reviewQueue(60)])
      .then(([validation, queue]) => setData({ validation, queue }))
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!data) return <Loading label="Loading validation metrics..." />;

  const v = data.validation;
  const cm = v.confusion_matrix;

  return (
    <div className="space-y-4">
      <DecisionSupportNotice />

      {/* ------------------------------------------------------ metrics */}
      {v.available ? (
        <>
          <div className="card">
            <div className="card-header">
              <div className="flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-slate-400" />
                <div>
                  <h3 className="card-title">Model Validation</h3>
                  <p className="card-sub">
                    Measured on a held-out test split of {num(v.test_size)} reports that the model
                    never saw during training. Training-set scores would flatter the model and
                    mislead the HSE team reading them.
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 grid grid-cols-2 md:grid-cols-5 gap-3">
              <MetricTile label="Accuracy" value={pct(v.accuracy, 1)} />
              <MetricTile label="Precision" value={pct(v.precision, 1)} />
              <MetricTile label="Recall" value={pct(v.recall, 1)} tone="good" />
              <MetricTile label="F1 Score" value={v.f1?.toFixed(3)} />
              <MetricTile label="ROC AUC" value={v.roc_auc?.toFixed(3)} />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Confusion Matrix</h3>
              </div>
              <div className="p-4">
                <table className="w-full text-[12.5px] border-collapse">
                  <thead>
                    <tr>
                      <th className="th"></th>
                      <th className="th text-center">Predicted Non-SIF</th>
                      <th className="th text-center">Predicted SIF</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="td font-semibold bg-slate-50">Actual Non-SIF</td>
                      <td className="td text-center bg-safe-50 font-bold text-safe-700 tabular-nums text-[15px]">
                        {num(cm.tn)}
                      </td>
                      <td className="td text-center bg-warn-50 text-warn-700 tabular-nums text-[15px]">
                        {num(cm.fp)}
                      </td>
                    </tr>
                    <tr>
                      <td className="td font-semibold bg-slate-50">Actual SIF</td>
                      <td className="td text-center bg-danger-50 font-bold text-danger-700 tabular-nums text-[15px]">
                        {num(cm.fn)}
                      </td>
                      <td className="td text-center bg-safe-50 font-bold text-safe-700 tabular-nums text-[15px]">
                        {num(cm.tp)}
                      </td>
                    </tr>
                  </tbody>
                </table>

                <div className="mt-3 p-3 rounded-md bg-slate-50 border border-slate-200">
                  <p className="text-[11.5px] text-slate-600 leading-snug">
                    <strong className="text-navy-800">The two errors are not equal.</strong> A false
                    positive ({num(cm.fp)}) costs an HSE professional a few minutes reviewing a
                    routine report. A false negative ({num(cm.fn)}) is a fatal-potential precursor
                    that goes back into the monthly queue and is never acted on. The threshold is
                    therefore tuned toward <strong>recall</strong>, and uncertain or critical-risk
                    reports are routed to human review rather than being auto-classified.
                  </p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Methodology</h3>
              </div>
              <div className="p-4 space-y-2.5 text-[12px] text-slate-600 leading-relaxed">
                <Row k="Train / test split" v={`${num(v.train_size)} / ${num(v.test_size)}`} />
                <Row k="Evaluated on" v={v.evaluated_on} />
                <Row
                  k="Outcome masking"
                  v={v.outcome_masking ? "Enabled" : "Disabled"}
                />
                <Row k="Labelled reports" v={num(v.reviewed_reports)} />
                <div className="pt-2 border-t border-slate-100">
                  <p className="text-[11.5px] leading-snug">
                    <strong className="text-navy-800">Why outcome masking matters.</strong> Injury
                    words are stripped from the text before training, so the model cannot learn
                    &ldquo;amputated &rarr; SIF&rdquo;. It is forced to learn from the circumstances
                    - the activity, equipment, energy source and control state. That is what lets it
                    work on a near-miss report where nobody was hurt and no outcome word exists.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="card p-5 border-warn-200 bg-warn-50">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-warn-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-[14px] font-bold text-warn-700">{v.message}</h3>
              <p className="text-[12.5px] text-warn-700/90 mt-2 leading-relaxed max-w-3xl">
                {v.explanation}
              </p>
              <p className="text-[12px] text-warn-700 mt-3 font-medium">
                No accuracy figures are shown, because inventing them would be worse than showing
                none.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* -------------------------------------------------- review queue */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="card-title">Low-Confidence / High-Risk Review Queue</h3>
              <p className="card-sub">
                Reports the model should not decide alone - either its confidence falls inside the
                uncertainty band, or the risk is Critical and a human must sign it off
              </p>
            </div>
          </div>
          <span className="chip bg-warn-50 text-warn-700 border-warn-200">
            <AlertTriangle className="w-3 h-3" />
            {num(v.review_queue_size)} awaiting review
          </span>
        </div>

        {data.queue.items.length === 0 ? (
          <Empty title="Review queue is empty" hint="No report currently requires human verification" />
        ) : (
          <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0">
                <tr>
                  <th className="th">Report ID</th>
                  <th className="th">Location</th>
                  <th className="th">Confidence</th>
                  <th className="th">Risk</th>
                  <th className="th">IOGP Rule</th>
                  <th className="th min-w-[240px]">Why review is required</th>
                </tr>
              </thead>
              <tbody>
                {data.queue.items.map((r) => (
                  <tr
                    key={r.report_id}
                    className="hover:bg-slate-50 cursor-pointer"
                    onClick={() => navigate(`/reports/${encodeURIComponent(r.report_id)}`)}
                  >
                    <td className="td font-mono text-[11.5px] text-info-700 whitespace-nowrap">
                      {r.report_id}
                    </td>
                    <td className="td whitespace-nowrap">{r.location}</td>
                    <td className="td">
                      <ConfidenceBar value={r.confidence} />
                    </td>
                    <td className="td">
                      <RiskBadge level={r.risk_level} />
                    </td>
                    <td className="td text-slate-600 whitespace-nowrap">{r.iogp_rule_name}</td>
                    <td className="td text-slate-600">{r.review_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card p-4">
        <h3 className="card-title mb-2">What production validation requires</h3>
        <ul className="text-[12.5px] text-slate-600 space-y-1.5 leading-relaxed list-disc pl-5">
          <li>300-500 reports independently classified by qualified HSE professionals</li>
          <li>Dual review, with disagreements adjudicated by a third reviewer</li>
          <li>Coverage of all nine Life-Saving Rules and both SIF and non-SIF outcomes</li>
          <li>Precision and recall measured against that human ground truth, not a proxy label</li>
          <li>Periodic drift monitoring as reporting practice and terminology change</li>
        </ul>
      </div>
    </div>
  );
}

function MetricTile({ label, value, tone }) {
  return (
    <div className="p-3 rounded-md border border-slate-200 bg-slate-50">
      <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
      <p
        className={`text-[20px] font-bold tabular-nums mt-0.5 ${
          tone === "good" ? "text-safe-700" : "text-navy-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-slate-500 shrink-0">{k}</span>
      <span className="text-navy-800 font-medium text-right">{v}</span>
    </div>
  );
}
