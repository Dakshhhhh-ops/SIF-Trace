import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Filter, Search, X } from "lucide-react";

import api from "../api";
import ReportAnalysis from "../components/ReportAnalysis";
import {
  ConfidenceBar,
  Empty,
  ErrorState,
  Loading,
  RiskBadge,
  SifBadge,
  StatusChip,
  num,
} from "../components/ui";

const PAGE_SIZE = 25;

const BLANK = {
  q: "",
  classification: "",
  report_type: "",
  location: "",
  activity: "",
  iogp_rule: "",
  risk_level: "",
  status: "",
  min_confidence: 0,
  max_confidence: 1,
  date_from: "",
  date_to: "",
};

export default function Reports() {
  const { reportId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [filters, setFilters] = useState(() => ({
    ...BLANK,
    location: searchParams.get("location") || "",
    activity: searchParams.get("activity") || "",
    iogp_rule: searchParams.get("iogp_rule") || "",
    classification: searchParams.get("classification") || "",
  }));
  const [debouncedQ, setDebouncedQ] = useState("");
  const [page, setPage] = useState(1);
  const [options, setOptions] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);

  // Debounce the free-text search so typing does not fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(filters.q), 300);
    return () => clearTimeout(id);
  }, [filters.q]);

  useEffect(() => {
    api.filters().then(setOptions).catch((e) => setError(e.message));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .reports({ ...filters, q: debouncedQ, page, page_size: PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filters, debouncedQ, page]);

  useEffect(load, [load]);

  // Deep link: /reports/:reportId opens the analysis panel directly.
  useEffect(() => {
    if (!reportId) return;
    api.report(reportId).then(setSelected).catch((e) => setError(e.message));
  }, [reportId]);

  const set = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };

  const activeCount = useMemo(
    () =>
      Object.entries(filters).filter(([k, v]) => {
        if (k === "min_confidence") return v > 0;
        if (k === "max_confidence") return v < 1;
        return v !== "" && v !== BLANK[k];
      }).length,
    [filters]
  );

  const closeDetail = () => {
    setSelected(null);
    if (reportId) navigate("/reports");
  };

  if (error && !data) return <ErrorState error={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------ filters */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="card-title">Safety Reports</h3>
              <p className="card-sub">
                {data ? `${num(data.total)} matching report${data.total === 1 ? "" : "s"}` : "Loading..."}
                {activeCount > 0 && ` - ${activeCount} filter${activeCount === 1 ? "" : "s"} active`}
              </p>
            </div>
          </div>
          {activeCount > 0 && (
            <button
              onClick={() => {
                setFilters(BLANK);
                setPage(1);
              }}
              className="btn-ghost"
            >
              <X className="w-3.5 h-3.5" /> Clear filters
            </button>
          )}
        </div>

        <div className="p-3 space-y-3">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              className="input pl-8"
              placeholder="Search across narratives - e.g. 'fire watch', 'isolation', 'confined space'"
              value={filters.q}
              onChange={(e) => set("q", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5">
            <Select label="Classification" value={filters.classification}
              onChange={(v) => set("classification", v)} options={options?.classifications} />
            <Select label="Report Type" value={filters.report_type}
              onChange={(v) => set("report_type", v)} options={options?.report_types} />
            <Select label="Location" value={filters.location}
              onChange={(v) => set("location", v)} options={options?.locations} />
            <Select label="Activity" value={filters.activity}
              onChange={(v) => set("activity", v)} options={options?.activities} />
            <Select label="IOGP Rule" value={filters.iogp_rule}
              onChange={(v) => set("iogp_rule", v)}
              options={options?.iogp_rules?.map((r) => ({ value: r.key, label: r.name }))} />
            <Select label="Risk Level" value={filters.risk_level}
              onChange={(v) => set("risk_level", v)} options={options?.risk_levels} />
            <Select label="Review Status" value={filters.status}
              onChange={(v) => set("status", v)} options={options?.statuses} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            <div>
              <label className="label">
                Confidence range: {Math.round(filters.min_confidence * 100)}% -{" "}
                {Math.round(filters.max_confidence * 100)}%
              </label>
              <div className="flex items-center gap-2">
                <input type="range" min="0" max="1" step="0.05" className="flex-1"
                  value={filters.min_confidence}
                  onChange={(e) => set("min_confidence", Math.min(+e.target.value, filters.max_confidence))} />
                <input type="range" min="0" max="1" step="0.05" className="flex-1"
                  value={filters.max_confidence}
                  onChange={(e) => set("max_confidence", Math.max(+e.target.value, filters.min_confidence))} />
              </div>
            </div>
            <div>
              <label className="label">Date from</label>
              <input type="date" className="input" value={filters.date_from}
                onChange={(e) => set("date_from", e.target.value)} />
            </div>
            <div>
              <label className="label">Date to</label>
              <input type="date" className="input" value={filters.date_to}
                onChange={(e) => set("date_to", e.target.value)} />
            </div>
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------- table */}
      <div className="card">
        {loading && !data ? (
          <Loading />
        ) : data?.items?.length === 0 ? (
          <Empty title="No reports match these filters" hint="Try widening the confidence range or clearing filters" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr>
                    <th className="th">Report ID</th>
                    <th className="th">Date</th>
                    <th className="th">Location</th>
                    <th className="th">Type</th>
                    <th className="th">Activity</th>
                    <th className="th min-w-[280px]">Narrative</th>
                    <th className="th">Classification</th>
                    <th className="th">Confidence</th>
                    <th className="th">Risk</th>
                    <th className="th">IOGP Rule</th>
                    <th className="th">Failed Barrier</th>
                    <th className="th">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map((r) => (
                    <tr key={r.report_id} className="hover:bg-slate-50 cursor-pointer"
                      onClick={() => setSelected(r)}>
                      <td className="td font-mono text-[11.5px] text-info-700 whitespace-nowrap">
                        {r.report_id}
                      </td>
                      <td className="td text-slate-500 tabular-nums whitespace-nowrap">{r.date || "-"}</td>
                      <td className="td whitespace-nowrap">{r.location}</td>
                      <td className="td text-slate-600 whitespace-nowrap">{r.report_type}</td>
                      <td className="td text-slate-600 whitespace-nowrap">{r.activity}</td>
                      <td className="td text-slate-700 max-w-[340px]">
                        <span className="line-clamp-2">{r.narrative}</span>
                      </td>
                      <td className="td"><SifBadge isSif={r.is_sif} /></td>
                      <td className="td"><ConfidenceBar value={r.confidence} /></td>
                      <td className="td"><RiskBadge level={r.risk_level} /></td>
                      <td className="td text-slate-600 whitespace-nowrap">{r.iogp_rule_name}</td>
                      <td className="td text-slate-600">
                        {r.failed_barriers?.length ? (
                          <span className="line-clamp-2">{r.failed_barriers.join("; ")}</span>
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>
                      <td className="td"><StatusChip status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-200">
              <p className="text-[12px] text-slate-500 tabular-nums">
                Page {data?.page} of {data?.pages} - {num(data?.total)} reports
              </p>
              <div className="flex gap-1.5">
                <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft className="w-3.5 h-3.5" /> Previous
                </button>
                <button className="btn-ghost" disabled={page >= (data?.pages || 1)}
                  onClick={() => setPage((p) => p + 1)}>
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {selected && <ReportAnalysis report={selected} onClose={closeDetail} />}
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  const items = (options || []).map((o) =>
    typeof o === "string" ? { value: o, label: o } : o
  );
  return (
    <div>
      <label className="label">{label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {items.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
