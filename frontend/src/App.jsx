import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  Activity,
  CheckSquare,
  Database,
  FileText,
  LayoutDashboard,
  Network,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldAlert,
} from "lucide-react";

import api from "./api";
import { DemoBanner } from "./components/ui";
import UploadDialog from "./components/UploadDialog";

import Dashboard from "./pages/Dashboard";
import Reports from "./pages/Reports";
import Patterns from "./pages/Patterns";
import IogpRules from "./pages/IogpRules";
import Validation from "./pages/Validation";
import SettingsPage from "./pages/Settings";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/patterns", label: "Precursor Patterns", icon: Network },
  { to: "/iogp-rules", label: "IOGP Life-Saving Rules", icon: ShieldAlert },
  { to: "/validation", label: "Validation", icon: CheckSquare },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (e) {
      setHealthError(e.message);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth, reloadKey]);

  const onDataChanged = () => {
    setReloadKey((k) => k + 1);
    refreshHealth();
  };

  const lastUpdated = health?.last_analysed
    ? new Date(health.last_analysed * 1000).toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "-";

  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* ------------------------------------------------------- sidebar */}
      <aside className="w-56 shrink-0 bg-navy-900 flex flex-col sticky top-0 h-screen">
        <div className="px-4 py-4 border-b border-navy-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-danger-600 rounded">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <div className="leading-tight">
              <h1 className="text-white font-bold text-[15px] tracking-tight">SIF-Trace</h1>
              <p className="text-navy-300 text-[10px] uppercase tracking-wider">
                Safety Intelligence
              </p>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-2.5 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-2.5 border-t border-navy-800 space-y-2">
          <button
            onClick={() => setUploadOpen(true)}
            className="w-full btn bg-navy-800 text-white border-navy-700 hover:bg-navy-700 justify-center"
          >
            <Database className="w-3.5 h-3.5" />
            Import CSV
          </button>
          <p className="text-[10px] text-navy-300 text-center leading-snug px-1">
            AI prioritises.<br />HSE decides.
          </p>
        </div>
      </aside>

      {/* ---------------------------------------------------------- main */}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="bg-white border-b border-slate-200 px-5 py-2.5 sticky top-0 z-20">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <h2 className="text-[15px] font-bold text-navy-900 tracking-tight">
                Indian E&amp;P Safety Intelligence Overview
              </h2>
              <p className="text-[11.5px] text-slate-500 mt-0.5 truncate">
                SIF precursor detection across unsafe acts, unsafe conditions and near misses
              </p>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <DemoBanner banner={health?.demo_banner} />

              <div className="text-right leading-tight hidden lg:block">
                <p className="text-[11px] text-slate-400 uppercase tracking-wide font-semibold">
                  Dataset
                </p>
                <p className="text-[12px] font-medium text-navy-800 max-w-[190px] truncate">
                  {health?.dataset_name || "None"}
                </p>
              </div>

              <div className="text-right leading-tight hidden xl:block">
                <p className="text-[11px] text-slate-400 uppercase tracking-wide font-semibold">
                  Last analysed
                </p>
                <p className="text-[12px] font-medium text-navy-800">{lastUpdated}</p>
              </div>

              <div className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    healthError ? "bg-danger-500" : "bg-safe-500"
                  }`}
                />
                <span className="text-[11.5px] text-slate-600">
                  {healthError ? "API offline" : `${(health?.total_reports || 0).toLocaleString("en-IN")} reports`}
                </span>
              </div>

              <button onClick={onDataChanged} className="btn-ghost" title="Refresh">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 p-5 min-w-0">
          {healthError ? (
            <div className="card p-6 border-danger-200 bg-danger-50 max-w-2xl">
              <h3 className="font-semibold text-danger-700 mb-1.5">Backend not reachable</h3>
              <p className="text-[12.5px] text-danger-700/90 mb-3">{healthError}</p>
              <pre className="text-[11.5px] bg-white border border-danger-200 rounded p-2.5 overflow-x-auto">
{`cd backend
../.venv/Scripts/python -m uvicorn main:app --port 8000`}
              </pre>
            </div>
          ) : (
            <Routes key={reloadKey}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/reports/:reportId" element={<Reports />} />
              <Route path="/patterns" element={<Patterns />} />
              <Route path="/iogp-rules" element={<IogpRules />} />
              <Route path="/validation" element={<Validation />} />
              <Route path="/settings" element={<SettingsPage onChanged={onDataChanged} />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          )}
        </main>
      </div>

      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onLoaded={onDataChanged}
      />
    </div>
  );
}
