import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpFromLine,
  Box,
  ClipboardCheck,
  Crosshair,
  Flame,
  MoveVertical,
  ShieldOff,
  Truck,
  ZapOff,
} from "lucide-react";

import api from "../api";
import { ConfidenceBar, ErrorState, Loading, num, pct } from "../components/ui";

const ICONS = {
  "shield-off": ShieldOff,
  box: Box,
  truck: Truck,
  "zap-off": ZapOff,
  flame: Flame,
  crosshair: Crosshair,
  "move-vertical": MoveVertical,
  "clipboard-check": ClipboardCheck,
  "arrow-up-from-line": ArrowUpFromLine,
};

export default function IogpRules() {
  const navigate = useNavigate();
  const [rules, setRules] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);

  const load = () => {
    setError(null);
    api.iogpRules().then(setRules).catch((e) => setError(e.message));
  };

  useEffect(load, []);

  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!rules) return <Loading label="Loading Life-Saving Rules..." />;

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <h3 className="card-title text-[14px]">IOGP Life-Saving Rules</h3>
        <p className="text-[12.5px] text-slate-600 mt-1.5 leading-relaxed max-w-4xl">
          The nine rules from IOGP Report 459, derived from analysis of over 370 fatalities in the
          upstream industry. Every report is mapped to the rule its circumstances engage. The
          mapping logic lives in a separate module from the model, so HSE teams can refine it
          without retraining anything. Select a rule to see the reports behind it.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {rules.map((r) => {
          const Icon = ICONS[r.icon] || ShieldOff;
          const isOpen = open === r.rule;
          const hot = r.sif_density >= 0.35 && r.total_reports > 0;

          return (
            <div
              key={r.rule}
              className={`card flex flex-col ${hot ? "border-danger-200" : ""}`}
            >
              <div className="p-4 flex-1">
                <div className="flex items-start gap-3">
                  <div
                    className={`p-2 rounded-md shrink-0 ${
                      hot ? "bg-danger-50 text-danger-600" : "bg-navy-50 text-navy-700"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-[13.5px] font-semibold text-navy-900 leading-tight">
                      {r.name}
                    </h4>
                    <p className="text-[11.5px] text-slate-500 mt-1 leading-snug">{r.statement}</p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 mt-3.5 pt-3 border-t border-slate-100">
                  <Stat label="Reports" value={num(r.total_reports)} />
                  <Stat label="SIF" value={num(r.sif_reports)} tone="danger" />
                  <Stat label="Density" value={pct(r.sif_density, 0)} />
                </div>

                <div className="mt-2.5">
                  <ConfidenceBar value={r.sif_density} showLabel={false} />
                </div>

                <div className="mt-3">
                  <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-wide">
                    Top associated precursor
                  </p>
                  <p className="text-[12px] text-navy-800 mt-0.5 leading-snug">
                    {r.top_precursor}
                  </p>
                </div>

                {isOpen && (
                  <div className="mt-3 pt-3 border-t border-slate-100 space-y-2.5">
                    <p className="text-[11.5px] text-slate-600 leading-relaxed">{r.description}</p>
                    {r.examples.length > 0 && (
                      <div>
                        <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
                          Example reports
                        </p>
                        <div className="space-y-1.5">
                          {r.examples.map((ex) => (
                            <button
                              key={ex.report_id}
                              onClick={() =>
                                navigate(`/reports/${encodeURIComponent(ex.report_id)}`)
                              }
                              className="w-full text-left p-2 rounded border border-slate-200 hover:border-info-300 hover:bg-info-50/40"
                            >
                              <div className="flex items-center gap-2 text-[10.5px] text-slate-500">
                                <span className="font-mono text-info-700">{ex.report_id}</span>
                                <span>{ex.location}</span>
                                <span className="ml-auto tabular-nums">
                                  {pct(ex.confidence, 0)}
                                </span>
                              </div>
                              <p className="text-[11.5px] text-navy-800 mt-0.5 leading-snug line-clamp-3">
                                {ex.narrative}
                              </p>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex border-t border-slate-200">
                <button
                  onClick={() => setOpen(isOpen ? null : r.rule)}
                  className="flex-1 px-3 py-2 text-[12px] font-medium text-navy-700 hover:bg-slate-50"
                >
                  {isOpen ? "Hide details" : "Details"}
                </button>
                <button
                  onClick={() => navigate(`/reports?iogp_rule=${r.rule}`)}
                  disabled={r.total_reports === 0}
                  className="flex-1 px-3 py-2 text-[12px] font-medium text-info-700 hover:bg-info-50 border-l border-slate-200 disabled:text-slate-300 disabled:hover:bg-transparent"
                >
                  Filter reports
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div>
      <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-wide">{label}</p>
      <p
        className={`text-[15px] font-bold tabular-nums leading-tight ${
          tone === "danger" ? "text-danger-600" : "text-navy-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
