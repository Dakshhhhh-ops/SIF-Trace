import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers, MapPin, Network } from "lucide-react";

import api from "../api";
import { Empty, ErrorState, Loading, RiskBadge, num, pct } from "../components/ui";

const FAMILIES = [
  { key: "", label: "All families", hint: "Every mined combination" },
  { key: "rule_barrier", label: "Rule + Barrier", hint: "e.g. Hot Work - Fire Watch Missing" },
  { key: "activity_barrier", label: "Activity + Barrier", hint: "e.g. Welding - Fire Watch Missing" },
  { key: "activity_location_barrier", label: "Activity + Site + Barrier", hint: "Localised to one site" },
  { key: "hazard_activity_location", label: "Hazard + Activity + Site", hint: "Energy-source clustering" },
];

export default function Patterns() {
  const navigate = useNavigate();
  const [family, setFamily] = useState("");
  const [patterns, setPatterns] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = () => {
    setError(null);
    setPatterns(null);
    api
      .patterns({ limit: 60, family: family || undefined })
      .then(setPatterns)
      .catch((e) => setError(e.message));
  };

  useEffect(load, [family]);

  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="card-title">Recurring Precursor Patterns</h3>
              <p className="card-sub">
                Classifying one report describes one report. A combination that repeats across sites
                is a systemic failure - and that is what an intervention should target. Patterns are
                mined from the reports themselves; a combination must recur at least 3 times to
                qualify, so a single odd report never becomes a &ldquo;pattern&rdquo;.
              </p>
            </div>
          </div>
        </div>

        <div className="p-3 flex flex-wrap gap-1.5">
          {FAMILIES.map((f) => (
            <button
              key={f.key}
              onClick={() => setFamily(f.key)}
              title={f.hint}
              className={`btn ${
                family === f.key
                  ? "bg-navy-800 text-white border-navy-800"
                  : "bg-white text-navy-700 border-slate-300 hover:bg-slate-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {!patterns ? (
        <Loading label="Mining precursor patterns..." />
      ) : patterns.length === 0 ? (
        <div className="card">
          <Empty
            title="No recurring patterns in this family"
            hint="Lower the minimum occurrence threshold in Settings, or load a larger dataset"
          />
        </div>
      ) : (
        <div className="space-y-2.5">
          {patterns.map((p) => {
            const open = expanded === p.pattern_id;
            return (
              <div key={p.pattern_id} className="card">
                <button
                  className="w-full text-left p-4 hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(open ? null : p.pattern_id)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <h4 className="text-[13.5px] font-semibold text-navy-900">{p.label}</h4>
                        <RiskBadge level={p.risk_level} />
                      </div>

                      <div className="flex items-center gap-4 mt-2 text-[12px] text-slate-500 flex-wrap">
                        <span>
                          <strong className="text-navy-900 tabular-nums text-[13px]">
                            {p.occurrences}
                          </strong>{" "}
                          occurrences
                        </span>
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" />
                          <strong className="text-navy-900 tabular-nums">{p.site_count}</strong>{" "}
                          site{p.site_count === 1 ? "" : "s"}
                        </span>
                        <span>
                          avg confidence{" "}
                          <strong className="text-navy-900 tabular-nums">
                            {pct(p.avg_confidence, 0)}
                          </strong>
                        </span>
                        <span>
                          max risk <strong className="text-navy-900">{p.max_risk}</strong>
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {p.sites.slice(0, 8).map((s) => (
                          <span
                            key={s}
                            className="chip bg-slate-50 text-slate-600 border-slate-200"
                          >
                            {s}
                          </span>
                        ))}
                        {p.sites.length > 8 && (
                          <span className="chip bg-slate-50 text-slate-400 border-slate-200">
                            +{p.sites.length - 8} more
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </button>

                {open && (
                  <div className="px-4 pb-4 border-t border-slate-100 pt-3 space-y-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
                      {Object.entries(p.components).map(([k, v]) => (
                        <div key={k}>
                          <p className="text-[10.5px] font-semibold text-slate-400 uppercase tracking-wide">
                            {k}
                          </p>
                          <p className="text-navy-800 font-medium mt-0.5">{v}</p>
                        </div>
                      ))}
                    </div>

                    <div>
                      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">
                        Example reports
                      </p>
                      <div className="space-y-2">
                        {p.example_reports.map((ex) => (
                          <button
                            key={ex.report_id}
                            onClick={() => navigate(`/reports/${encodeURIComponent(ex.report_id)}`)}
                            className="w-full text-left p-2.5 rounded-md border border-slate-200 hover:border-info-300 hover:bg-info-50/40"
                          >
                            <div className="flex items-center gap-2 text-[11.5px] text-slate-500">
                              <span className="font-mono text-info-700">{ex.report_id}</span>
                              <span>{ex.location}</span>
                              <span className="tabular-nums">{ex.date}</span>
                              <span className="ml-auto tabular-nums">
                                {pct(ex.confidence, 0)} confidence
                              </span>
                            </div>
                            <p className="text-[12.5px] text-navy-800 mt-1 leading-snug">
                              {ex.narrative}
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
