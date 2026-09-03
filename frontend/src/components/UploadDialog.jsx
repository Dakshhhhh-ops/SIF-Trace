import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Upload, X } from "lucide-react";
import api from "../api";

/**
 * CSV import.
 *
 * The backend infers column mapping from names and, failing that, from content,
 * so the operator sees what was detected and can correct it before trusting any
 * number on the dashboard.
 */
export default function UploadDialog({ open, onClose, onLoaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isDemo, setIsDemo] = useState(true);

  if (!open) return null;

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setBusy(false);
  };

  const close = () => {
    reset();
    onClose();
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.upload(file, isDemo);
      setResult(res);
      onLoaded?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const restoreDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.reloadDemo();
      onLoaded?.();
      close();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="card-header sticky top-0 bg-white">
          <div>
            <h3 className="card-title">Import Safety Report CSV</h3>
            <p className="card-sub">
              Columns are detected automatically - narrative, date, location, activity and any
              existing SIF label.
            </p>
          </div>
          <button onClick={close} className="p-1 hover:bg-slate-100 rounded">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <label className="block border-2 border-dashed border-slate-300 rounded-lg p-6 text-center cursor-pointer hover:border-info-500 hover:bg-info-50/40 transition-colors">
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setResult(null);
                setError(null);
              }}
            />
            <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
            <p className="text-[13px] font-medium text-navy-800">
              {file ? file.name : "Choose a CSV file"}
            </p>
            <p className="text-[11.5px] text-slate-500 mt-1">
              {file
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                : "Any HSSE export - column names do not need to match"}
            </p>
          </label>

          <label className="flex items-start gap-2.5 p-3 rounded-md bg-warn-50 border border-warn-200 cursor-pointer">
            <input
              type="checkbox"
              checked={isDemo}
              onChange={(e) => setIsDemo(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-[11.5px] text-warn-700 leading-snug">
              <strong>This is demo / synthetic data.</strong> Leave this ticked unless the file
              contains genuine operational records. When ticked, every view is labelled
              &ldquo;DEMO DATA - NOT ACTUAL OIL RECORDS&rdquo; so figures can never be mistaken for
              real OIL statistics.
            </span>
          </label>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-danger-50 border border-danger-200">
              <AlertTriangle className="w-4 h-4 text-danger-600 shrink-0 mt-0.5" />
              <p className="text-[12px] text-danger-700">{error}</p>
            </div>
          )}

          {result && (
            <div className="rounded-md bg-safe-50 border border-safe-200 p-3">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-safe-600" />
                <p className="text-[13px] font-semibold text-safe-700">
                  Loaded and analysed {result.rows_loaded?.toLocaleString("en-IN")} reports in{" "}
                  {result.analysis_seconds}s
                </p>
              </div>

              <div className="text-[11.5px] text-navy-700 space-y-1.5">
                <div>
                  <span className="font-semibold">Detected columns: </span>
                  {Object.entries(result.mapping || {})
                    .map(([k, v]) => `${k} <- ${v}`)
                    .join(", ") || "none"}
                </div>
                {result.has_ground_truth && (
                  <div className="text-safe-700">
                    Verified SIF labels found - the model was retrained and validation metrics are
                    computed from this dataset.
                  </div>
                )}
                {(result.warnings || []).map((w, i) => (
                  <div key={i} className="text-warn-700">
                    {w}
                  </div>
                ))}
                {result.unmapped_columns?.length > 0 && (
                  <div className="text-slate-500">
                    Unused columns: {result.unmapped_columns.join(", ")}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            <button onClick={restoreDemo} className="btn-ghost" disabled={busy}>
              Restore demo corpus
            </button>
            <div className="flex gap-2">
              <button onClick={close} className="btn-ghost">
                {result ? "Done" : "Cancel"}
              </button>
              <button onClick={submit} className="btn-primary" disabled={!file || busy}>
                {busy ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Analysing...
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" /> Upload &amp; analyse
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
