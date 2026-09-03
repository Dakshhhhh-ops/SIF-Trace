import { useEffect, useState } from "react";
import { Check, Database, KeyRound, Loader2, RotateCcw, Sliders, Sparkles } from "lucide-react";

import api, { auth } from "../api";
import { DecisionSupportNotice, ErrorState, Loading, num, pct } from "../components/ui";

const SLIDERS = [
  {
    key: "sif_confidence",
    label: "SIF confidence threshold",
    hint: "A report is flagged SIF-Potential at or above this blended confidence. Lower it to catch more precursors at the cost of more review work.",
    min: 0.2, max: 0.8, step: 0.01, format: pct,
  },
  {
    key: "review_low",
    label: "Review band - lower bound",
    hint: "Reports between the two bounds are treated as too uncertain for the model to decide alone.",
    min: 0.1, max: 0.6, step: 0.01, format: pct,
  },
  {
    key: "review_high",
    label: "Review band - upper bound",
    hint: "Above this, the model is considered confident enough to classify without mandatory review.",
    min: 0.4, max: 0.95, step: 0.01, format: pct,
  },
  {
    key: "risk_critical",
    label: "Risk threshold - Critical",
    hint: "Composite risk at or above this is Critical and always routed to HSE review.",
    min: 0.5, max: 0.95, step: 0.01, format: (v) => v.toFixed(2),
  },
  {
    key: "risk_high",
    label: "Risk threshold - High",
    min: 0.3, max: 0.85, step: 0.01, format: (v) => v.toFixed(2),
  },
  {
    key: "risk_medium",
    label: "Risk threshold - Medium",
    min: 0.1, max: 0.6, step: 0.01, format: (v) => v.toFixed(2),
  },
];

const COUNTERS = [
  {
    key: "min_reports_for_ranking",
    label: "Minimum reports before a site is ranked",
    hint: "Stops a location with 1 report and 1 SIF appearing as a 100%-density crisis.",
    min: 1, max: 100,
  },
  {
    key: "min_pattern_occurrences",
    label: "Minimum occurrences to qualify as a pattern",
    hint: "A combination must repeat at least this often before it is called a recurring pattern.",
    min: 2, max: 30,
  },
];

export default function Settings({ onChanged }) {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [token, setToken] = useState(auth.get());
  const [tokenSaved, setTokenSaved] = useState(false);

  const [demoText, setDemoText] = useState(
    "Worker entered confined space without gas testing and permit verification."
  );
  const [demoResult, setDemoResult] = useState(null);
  const [demoBusy, setDemoBusy] = useState(false);

  const load = () => {
    setError(null);
    api
      .settings()
      .then((s) => {
        setSettings(s);
        setDraft(s.thresholds);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await api.updateThresholds(draft);
      setSaved(true);
      onChanged?.();
      setTimeout(() => setSaved(false), 2200);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const runDemo = async () => {
    setDemoBusy(true);
    try {
      setDemoResult(await api.analyse(demoText));
    } catch (e) {
      setError(e.message);
    } finally {
      setDemoBusy(false);
    }
  };

  if (error && !settings) return <ErrorState error={error} onRetry={load} />;
  if (!settings || !draft) return <Loading label="Loading settings..." />;

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings.thresholds);

  return (
    <div className="space-y-4">
      <DecisionSupportNotice />

      {/* ---------------------------------------------- live analysis */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="card-title">Analyse a Report</h3>
              <p className="card-sub">
                Paste any narrative to run the full pipeline live - extraction, classification, IOGP
                mapping and risk
              </p>
            </div>
          </div>
        </div>
        <div className="p-4 space-y-3">
          <textarea
            className="input min-h-[76px] resize-y"
            value={demoText}
            onChange={(e) => setDemoText(e.target.value)}
            placeholder="e.g. Hot work was carried out on the separator without a fire watch..."
          />
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={runDemo} className="btn-primary" disabled={demoBusy || demoText.length < 10}>
              {demoBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              Analyse
            </button>
            {[
              "Maintenance started after confirming isolation and zero-energy state.",
              "Welder was cutting on a line at the GGS while no fire watch was present.",
              "Operator bypassed the ESD interlock without authorisation.",
            ].map((s, i) => (
              <button key={i} onClick={() => setDemoText(s)} className="btn-ghost text-[11.5px]">
                Example {i + 1}
              </button>
            ))}
          </div>

          {demoResult && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3.5 space-y-2 text-[12.5px]">
              <div className="flex items-center gap-3 flex-wrap">
                <span
                  className={`font-bold ${
                    demoResult.is_sif ? "text-danger-600" : "text-safe-600"
                  }`}
                >
                  {demoResult.classification}
                </span>
                <span className="text-slate-500 tabular-nums">
                  confidence {pct(demoResult.confidence, 0)}
                </span>
                <span className="text-slate-500">risk {demoResult.risk_level}</span>
              </div>
              <Line k="Activity" v={demoResult.activity} />
              <Line k="Hazard" v={demoResult.hazard} />
              <Line k="Exposure" v={demoResult.exposure} />
              <Line k="IOGP rule" v={demoResult.iogp_rule_name} />
              <Line k="Failed barriers" v={demoResult.failed_barriers?.join("; ") || "none"} />
              <Line k="Controls in place" v={demoResult.present_barriers?.join("; ") || "none stated"} />
              <Line k="Precursors" v={demoResult.precursors?.join("; ") || "none detected"} />
              <Line k="Action" v={demoResult.recommended_action} />
              <p className="text-[11.5px] text-slate-500 pt-1.5 border-t border-slate-200 leading-snug">
                {demoResult.iogp_explanation}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ----------------------------------------------- write access */}
      {settings.write_protected && (
        <div className="card">
          <div className="card-header">
            <div className="flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-slate-400" />
              <div>
                <h3 className="card-title">Write Access</h3>
                <p className="card-sub">
                  This deployment is read-only. Viewing needs nothing; uploading a dataset or
                  changing thresholds requires the access token, so a public link cannot alter
                  what everyone else sees.
                </p>
              </div>
            </div>
          </div>
          <div className="p-4 flex items-end gap-2 flex-wrap">
            <div className="flex-1 min-w-[240px]">
              <label className="label">Access token</label>
              <input
                type="password"
                className="input"
                value={token}
                placeholder="paste the SIF_ADMIN_TOKEN value"
                onChange={(e) => {
                  setToken(e.target.value);
                  setTokenSaved(false);
                }}
              />
            </div>
            <button
              className="btn-primary"
              onClick={() => {
                auth.set(token.trim());
                setTokenSaved(true);
                setTimeout(() => setTokenSaved(false), 2200);
              }}
            >
              {tokenSaved ? <Check className="w-3.5 h-3.5" /> : null}
              {tokenSaved ? "Saved" : "Save token"}
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------- thresholds */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="card-title">Detection Thresholds</h3>
              <p className="card-sub">
                Defaults favour recall: missing a fatal-potential precursor costs far more than an
                extra report in the review queue
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <button onClick={() => setDraft(settings.thresholds)} className="btn-ghost">
                <RotateCcw className="w-3.5 h-3.5" /> Reset
              </button>
            )}
            <button onClick={save} className="btn-primary" disabled={!dirty || saving}>
              {saving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : saved ? (
                <Check className="w-3.5 h-3.5" />
              ) : null}
              {saved ? "Applied" : "Apply"}
            </button>
          </div>
        </div>

        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          {SLIDERS.map((s) => (
            <div key={s.key}>
              <div className="flex items-center justify-between">
                <label className="text-[12px] font-medium text-navy-800">{s.label}</label>
                <span className="text-[12px] font-bold text-navy-900 tabular-nums">
                  {s.format(draft[s.key])}
                </span>
              </div>
              <input
                type="range"
                className="w-full mt-1.5"
                min={s.min}
                max={s.max}
                step={s.step}
                value={draft[s.key]}
                onChange={(e) => setDraft({ ...draft, [s.key]: +e.target.value })}
              />
              {s.hint && <p className="text-[11px] text-slate-500 mt-1 leading-snug">{s.hint}</p>}
            </div>
          ))}

          {COUNTERS.map((c) => (
            <div key={c.key}>
              <label className="text-[12px] font-medium text-navy-800">{c.label}</label>
              <input
                type="number"
                className="input mt-1.5"
                min={c.min}
                max={c.max}
                value={draft[c.key]}
                onChange={(e) => setDraft({ ...draft, [c.key]: +e.target.value })}
              />
              {c.hint && <p className="text-[11px] text-slate-500 mt-1 leading-snug">{c.hint}</p>}
            </div>
          ))}
        </div>
      </div>

      {/* ------------------------------------------- dataset + model */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-header">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-slate-400" />
              <h3 className="card-title">Dataset</h3>
            </div>
          </div>
          <div className="p-4 space-y-2 text-[12.5px]">
            <Line k="Name" v={settings.dataset.name} />
            <Line k="Reports" v={num(settings.dataset.rows)} />
            <Line
              k="Mode"
              v={settings.dataset.is_demo ? "DEMO - not actual OIL records" : "Operational data"}
            />
            <Line
              k="Verified SIF labels"
              v={settings.dataset.has_ground_truth ? "Present" : "Not available"}
            />
            <Line k="Analysis time" v={`${settings.dataset.analysis_seconds}s`} />
            <Line
              k="Last refreshed"
              v={
                settings.dataset.last_analysed
                  ? new Date(settings.dataset.last_analysed * 1000).toLocaleString("en-IN")
                  : "-"
              }
            />
            {settings.dataset.load_info?.mapping && (
              <div className="pt-2 border-t border-slate-100">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
                  Detected column mapping
                </p>
                <div className="font-mono text-[11px] text-slate-600 space-y-0.5">
                  {Object.entries(settings.dataset.load_info.mapping).map(([k, v]) => (
                    <div key={k}>
                      {k} &larr; {v}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Model</h3>
          </div>
          <div className="p-4 space-y-2 text-[12.5px]">
            <Line k="Type" v={settings.model.type} />
            <Line k="Trained" v={settings.model.trained ? "Yes" : "Rule engine only"} />
            <Line k="Outcome masking" v={settings.model.outcome_masking ? "Enabled" : "Disabled"} />
            <Line k="Model / rule blend" v={`${pct(settings.model.blend_model_weight, 0)} model`} />
            {settings.model.metrics?.f1 && (
              <>
                <div className="pt-2 border-t border-slate-100" />
                <Line k="Accuracy" v={pct(settings.model.metrics.accuracy, 1)} />
                <Line k="Precision" v={pct(settings.model.metrics.precision, 1)} />
                <Line k="Recall" v={pct(settings.model.metrics.recall, 1)} />
                <Line k="F1" v={settings.model.metrics.f1?.toFixed(3)} />
                <Line k="ROC AUC" v={settings.model.metrics.roc_auc?.toFixed(3)} />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Line({ k, v }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-slate-500 shrink-0">{k}</span>
      <span className="text-navy-800 font-medium text-right break-words">{v}</span>
    </div>
  );
}
