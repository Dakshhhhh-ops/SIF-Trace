import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ClipboardList,
  FileText,
  Gauge,
  MapPin,
  Network,
  ShieldAlert,
  Target,
} from "lucide-react";

import api from "../api";
import {
  ConfidenceBar,
  DecisionSupportNotice,
  Empty,
  ErrorState,
  KpiCard,
  Loading,
  RiskBadge,
  num,
  pct,
} from "../components/ui";

const RISK_FILL = {
  Critical: "#dc2626",
  High: "#d97706",
  Medium: "#2563eb",
  Low: "#16a34a",
  Unranked: "#94a3b8",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null);
    Promise.all([
      api.kpis(),
      api.siteRanking(),
      api.activityRanking(),
      api.iogpRules(),
      api.headlinePatterns(6),
      api.alerts(10),
    ])
      .then(([kpis, sites, activities, rules, patterns, alerts]) =>
        setData({ kpis, sites, activities, rules, patterns, alerts })
      )
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!data) return <Loading label="Loading safety intelligence..." />;

  const { kpis, sites, activities, rules, patterns, alerts } = data;
  const rankedSites = sites.filter((s) => s.ranked);

  const sifSplit = [
    { name: "SIF-Potential", value: kpis.sif_reports, fill: "#dc2626" },
    { name: "Non-SIF-Potential", value: kpis.total_reports - kpis.sif_reports, fill: "#16a34a" },
  ];

  const ruleChart = rules
    .filter((r) => r.total_reports > 0)
    .map((r) => ({
      name: r.name.replace(" Safety Controls", " Controls").replace("Safe Mechanical ", ""),
      total: r.total_reports,
      sif: r.sif_reports,
    }));

  return (
    <div className="space-y-4">
      <DecisionSupportNotice />

      {/* ------------------------------------------------------------ KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={FileText}
          label="Total Reports Analysed"
          value={num(kpis.total_reports)}
          sub={`Processed in ${kpis.analysis_seconds}s`}
        />
        <KpiCard
          icon={AlertTriangle}
          label="SIF-Potential Reports"
          value={num(kpis.sif_reports)}
          sub={`${num(kpis.critical_reports)} at critical risk`}
          tone="danger"
        />
        <KpiCard
          icon={Gauge}
          label="SIF Density"
          value={pct(kpis.sif_density)}
          sub="Share carrying fatal potential"
          tone="warn"
          hint="SIF-potential reports divided by total reports"
        />
        <KpiCard
          icon={MapPin}
          label="High-Risk Sites"
          value={num(kpis.high_risk_sites)}
          sub={`of ${rankedSites.length} ranked locations`}
          tone="danger"
          hint="Sites whose SIF density is significantly above the corpus baseline"
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={ClipboardList}
          label="Awaiting HSE Review"
          value={num(kpis.awaiting_review)}
          sub="Low confidence or critical risk"
          tone="info"
        />
        <KpiCard
          icon={Target}
          label="High-Confidence Alerts"
          value={num(kpis.high_confidence_alerts)}
          sub="Above the uncertainty band"
          tone="danger"
        />
        <KpiCard
          icon={ShieldAlert}
          label="Most Frequent IOGP Rule"
          value={<span className="text-[15px] leading-tight">{kpis.most_frequent_rule}</span>}
          sub="Across SIF-potential reports"
          tone="warn"
        />
        <KpiCard
          icon={Network}
          label="Critical Precursor Patterns"
          value={num(kpis.critical_patterns)}
          sub="Recurring high-risk combinations"
          tone="danger"
        />
      </div>

      {/* ------------------------------------------- risk overview + rules */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">SIF Risk Overview</h3>
              <p className="card-sub">Distribution of fatal potential</p>
            </div>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={170}>
              <PieChart>
                <Pie
                  data={sifSplit}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={72}
                  paddingAngle={2}
                >
                  {sifSplit.map((d, i) => (
                    <Cell key={i} fill={d.fill} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => num(v)} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1.5 mt-2">
              {sifSplit.map((d) => (
                <div key={d.name} className="flex items-center justify-between text-[12px]">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-sm" style={{ background: d.fill }} />
                    {d.name}
                  </span>
                  <span className="font-semibold tabular-nums">
                    {num(d.value)}{" "}
                    <span className="text-slate-400 font-normal">
                      ({pct(d.value / kpis.total_reports, 1)})
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card lg:col-span-2">
          <div className="card-header">
            <div>
              <h3 className="card-title">IOGP Life-Saving Rule Distribution</h3>
              <p className="card-sub">Reports mapped to each rule, and how many carry fatal potential</p>
            </div>
          </div>
          <div className="p-4">
            {ruleChart.length === 0 ? (
              <Empty title="No reports mapped to a Life-Saving Rule" />
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={ruleChart} margin={{ top: 4, right: 8, left: 0, bottom: 44 }}>
                  <XAxis
                    dataKey="name"
                    angle={-32}
                    textAnchor="end"
                    interval={0}
                    tick={{ fontSize: 10, fill: "#475569" }}
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#475569" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 6 }}
                    formatter={(v, n) => [num(v), n === "sif" ? "SIF-potential" : "Total reports"]}
                  />
                  <Bar dataKey="total" fill="#cbd5e1" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="sif" fill="#dc2626" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* -------------------------------------------------- site ranking */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Site Risk Ranking by SIF-Precursor Density</h3>
            <p className="card-sub">
              Ranked on density (SIF reports / total reports), never raw count - a site filing more
              reports is not automatically more dangerous. Each site is compared against the corpus
              baseline of {pct(kpis.sif_density)} and must be statistically significant (z &ge; 1.64)
              before being flagged High or Critical.
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr>
                <th className="th">Site</th>
                <th className="th text-right">Total</th>
                <th className="th text-right">SIF</th>
                <th className="th">SIF Density</th>
                <th className="th text-right">vs Baseline</th>
                <th className="th">Risk</th>
                <th className="th">Dominant IOGP Rule</th>
                <th className="th">Top Precursor</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => (
                <tr
                  key={s.key}
                  className="hover:bg-slate-50 cursor-pointer"
                  onClick={() => navigate(`/reports?location=${encodeURIComponent(s.key)}`)}
                >
                  <td className="td font-medium text-navy-900">{s.key}</td>
                  <td className="td text-right tabular-nums">{num(s.total_reports)}</td>
                  <td className="td text-right tabular-nums font-semibold text-danger-600">
                    {num(s.sif_reports)}
                  </td>
                  <td className="td">
                    <ConfidenceBar value={s.sif_density} />
                  </td>
                  <td className="td text-right tabular-nums">
                    <span
                      className={
                        s.density_ratio >= 1.15
                          ? "text-danger-600 font-semibold"
                          : s.density_ratio < 0.9
                          ? "text-safe-600"
                          : "text-slate-500"
                      }
                    >
                      {s.density_ratio?.toFixed(2)}x
                    </span>
                    {s.significant && <span className="text-[10px] text-slate-400 ml-1">sig.</span>}
                  </td>
                  <td className="td">
                    <RiskBadge level={s.risk_level} />
                  </td>
                  <td className="td text-slate-600">{s.dominant_rule}</td>
                  <td className="td text-slate-600">{s.top_precursor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* --------------------------------- activity ranking + patterns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Activity Risk Ranking</h3>
              <p className="card-sub">Which work activities carry the most fatal potential</p>
            </div>
          </div>
          <div className="overflow-x-auto max-h-[330px] overflow-y-auto">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0">
                <tr>
                  <th className="th">Activity</th>
                  <th className="th text-right">Total</th>
                  <th className="th text-right">SIF</th>
                  <th className="th">Density</th>
                  <th className="th">Risk</th>
                </tr>
              </thead>
              <tbody>
                {activities.map((a) => (
                  <tr
                    key={a.key}
                    className="hover:bg-slate-50 cursor-pointer"
                    onClick={() => navigate(`/reports?activity=${encodeURIComponent(a.key)}`)}
                  >
                    <td className="td font-medium text-navy-900">{a.key}</td>
                    <td className="td text-right tabular-nums">{num(a.total_reports)}</td>
                    <td className="td text-right tabular-nums font-semibold text-danger-600">
                      {num(a.sif_reports)}
                    </td>
                    <td className="td">
                      <ConfidenceBar value={a.sif_density} />
                    </td>
                    <td className="td">
                      <RiskBadge level={a.risk_level} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Recurring Precursor Patterns</h3>
              <p className="card-sub">
                Combinations extracted from the reports themselves, not preset categories
              </p>
            </div>
            <button onClick={() => navigate("/patterns")} className="btn-ghost">
              View all
            </button>
          </div>
          <div className="p-3 space-y-2 max-h-[330px] overflow-y-auto">
            {patterns.length === 0 ? (
              <Empty
                title="No recurring patterns yet"
                hint="A combination must repeat at least 3 times to qualify"
              />
            ) : (
              patterns.map((p) => (
                <div
                  key={p.pattern_id}
                  className="p-2.5 rounded-md border border-slate-200 hover:border-slate-300 bg-white"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[12.5px] font-semibold text-navy-900 leading-snug">
                      {p.label}
                    </p>
                    <RiskBadge level={p.risk_level} />
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-[11.5px] text-slate-500">
                    <span>
                      <strong className="text-navy-800 tabular-nums">{p.occurrences}</strong>{" "}
                      occurrences
                    </span>
                    <span>
                      <strong className="text-navy-800 tabular-nums">{p.site_count}</strong> site
                      {p.site_count === 1 ? "" : "s"}
                    </span>
                    <span className="tabular-nums">avg {pct(p.avg_confidence, 0)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------- alerts */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Recent SIF Alerts</h3>
            <p className="card-sub">Highest-priority reports requiring HSE attention</p>
          </div>
          <button onClick={() => navigate("/reports?classification=SIF-Potential")} className="btn-ghost">
            All SIF reports
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr>
                <th className="th">Report ID</th>
                <th className="th">Location</th>
                <th className="th">Date</th>
                <th className="th">Confidence</th>
                <th className="th">IOGP Rule</th>
                <th className="th">Risk</th>
                <th className="th">Status</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr
                  key={a.report_id}
                  className="hover:bg-slate-50 cursor-pointer"
                  onClick={() => navigate(`/reports/${encodeURIComponent(a.report_id)}`)}
                >
                  <td className="td font-mono text-[11.5px] text-info-700">{a.report_id}</td>
                  <td className="td">{a.location}</td>
                  <td className="td text-slate-500 tabular-nums">{a.date || "-"}</td>
                  <td className="td">
                    <ConfidenceBar value={a.confidence} />
                  </td>
                  <td className="td text-slate-600">{a.iogp_rule_name}</td>
                  <td className="td">
                    <RiskBadge level={a.risk_level} />
                  </td>
                  <td className="td text-slate-500">{a.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
