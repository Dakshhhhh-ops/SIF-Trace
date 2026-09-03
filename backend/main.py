"""
SIF-Trace REST API.

    uvicorn main:app --reload --port 8000    (run from the backend/ directory)

Serves every dashboard view from one in-memory analysed dataset, so the
expensive NLP work happens once per upload rather than once per request.
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sif import knowledge as kb
from sif.config import DECISION_SUPPORT_NOTICE, DEMO_BANNER, SHOW_DEMO_BANNER, TAGLINE
from sif.data_loader import DataLoadError
from sif.pipeline import Pipeline

DEMO_CSV = Path(__file__).resolve().parents[1] / "data" / "sif_reports.csv"

pipeline = Pipeline()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the demo corpus at startup so the dashboard is never empty."""
    if DEMO_CSV.exists():
        try:
            pipeline.load_path_cached(DEMO_CSV, is_demo=True)
        except DataLoadError as exc:  # pragma: no cover - defensive
            print(f"[SIF-Trace] demo corpus not loaded: {exc}")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="SIF-Trace API",
    description=(
        "AI/NLP engine detecting Serious Injury & Fatality (SIF) precursors in "
        "unsafe-act, unsafe-condition and near-miss reports. " + TAGLINE
    ),
    version="1.0.0",
)

# Origins allowed to call the API. Local dev hosts are always permitted; add
# deployed origins with  SIF_ALLOWED_ORIGINS="https://a.example,https://b.example"
# When the frontend is served by this same app (the deployed layout below),
# requests are same-origin and CORS is not involved at all.
_DEFAULT_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:8000", "http://127.0.0.1:8000",
]
_env_origins = [o.strip() for o in os.getenv("SIF_ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _env_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Write protection
#
# Read endpoints are public - the dashboard is meant to be looked at. But upload
# and threshold changes mutate GLOBAL state that every viewer sees, so on a
# public URL they must not be open to anyone who has the link.
#
# Set SIF_ADMIN_TOKEN to require  X-SIF-Token: <value>  on mutating endpoints.
# If it is unset the API stays fully open, which is correct for a laptop demo
# and is reported by /api/health so the state is never a surprise.
# --------------------------------------------------------------------------

ADMIN_TOKEN = os.getenv("SIF_ADMIN_TOKEN", "").strip()


def require_write_access(x_sif_token: str | None = Header(default=None)) -> None:
    if not ADMIN_TOKEN:
        return
    if not x_sif_token or not secrets.compare_digest(x_sif_token, ADMIN_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="This deployment is read-only. A valid X-SIF-Token header is "
                   "required to upload data or change thresholds.",
        )


def _require_data() -> None:
    if not pipeline.dataset.loaded:
        raise HTTPException(
            status_code=409,
            detail="No dataset loaded. Upload a CSV of safety reports to begin.",
        )


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    d = pipeline.dataset
    return {
        "status": "ok",
        "tagline": TAGLINE,
        "notice": DECISION_SUPPORT_NOTICE,
        "dataset_loaded": d.loaded,
        "dataset_name": d.name,
        "is_demo": d.is_demo,
        "demo_banner": DEMO_BANNER if (d.is_demo and SHOW_DEMO_BANNER) else "",
        "total_reports": len(d.records),
        "model_trained": d.model_trained,
        "last_analysed": d.analysed_at,
        "analysis_seconds": d.analysis_seconds,
        "write_protected": bool(ADMIN_TOKEN),
    }


@app.get("/api/kpis")
def kpis() -> dict[str, Any]:
    _require_data()
    return pipeline.kpis()


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


@app.get("/api/reports")
def reports(
    q: str | None = Query(None, description="free-text search across narratives"),
    classification: str | None = None,
    report_type: str | None = None,
    location: str | None = None,
    activity: str | None = None,
    iogp_rule: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    min_confidence: float = 0.0,
    max_confidence: float = 1.0,
    date_from: str | None = None,
    date_to: str | None = None,
    needs_review: bool | None = None,
    sort: str = "risk_score",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _require_data()
    rows = pipeline.dataset.records

    def keep(r: dict) -> bool:
        if q and q.lower() not in (r.get("narrative") or "").lower():
            return False
        if classification and r["classification"] != classification:
            return False
        if report_type and r["report_type"] != report_type:
            return False
        if location and r["location"] != location:
            return False
        if activity and r["activity"] != activity:
            return False
        if iogp_rule and r["iogp_rule"] != iogp_rule:
            return False
        if risk_level and r["risk_level"] != risk_level:
            return False
        if status and r["status"] != status:
            return False
        if not (min_confidence <= r["confidence"] <= max_confidence):
            return False
        if needs_review is not None and bool(r["needs_review"]) != needs_review:
            return False
        if date_from and (r["date"] or "") < date_from:
            return False
        if date_to and (r["date"] or "9999") > date_to:
            return False
        return True

    filtered = [r for r in rows if keep(r)]
    reverse = order.lower() != "asc"
    if sort in {"risk_score", "confidence", "date", "report_id", "location"}:
        filtered.sort(key=lambda r: (r.get(sort) is None, r.get(sort)), reverse=reverse)

    page = max(1, page)
    page_size = max(1, min(500, page_size))
    start = (page - 1) * page_size
    return {
        "total": len(filtered),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(filtered) // page_size)),
        "items": filtered[start : start + page_size],
    }


@app.get("/api/reports/{report_id}")
def report_detail(report_id: str) -> dict[str, Any]:
    _require_data()
    rec = pipeline.get_report(report_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found.")
    return rec


@app.get("/api/filters")
def filter_options() -> dict[str, Any]:
    _require_data()
    recs = pipeline.dataset.records
    uniq = lambda f: sorted({r[f] for r in recs if r.get(f)})  # noqa: E731
    return {
        "classifications": ["SIF-Potential", "Non-SIF-Potential"],
        "report_types": uniq("report_type"),
        "locations": uniq("location"),
        "activities": uniq("activity"),
        "risk_levels": ["Critical", "High", "Medium", "Low"],
        "statuses": uniq("status"),
        "iogp_rules": [
            {"key": k, "name": v["name"]} for k, v in kb.IOGP_RULES.items()
        ],
        "date_range": {
            "min": min((r["date"] for r in recs if r["date"]), default=None),
            "max": max((r["date"] for r in recs if r["date"]), default=None),
        },
    }


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------


@app.get("/api/rankings/sites")
def site_ranking() -> list[dict[str, Any]]:
    _require_data()
    return pipeline.site_ranking()


@app.get("/api/rankings/activities")
def activity_ranking() -> list[dict[str, Any]]:
    _require_data()
    return pipeline.activity_ranking()


@app.get("/api/iogp-rules")
def iogp_rules() -> list[dict[str, Any]]:
    _require_data()
    return pipeline.rule_distribution()


@app.get("/api/patterns")
def patterns(limit: int = 40, family: str | None = None) -> list[dict[str, Any]]:
    _require_data()
    pats = pipeline.patterns(limit=500)
    if family:
        pats = [p for p in pats if p["family"] == family]
    return pats[:limit]


@app.get("/api/patterns/headline")
def headline_patterns(n: int = 8) -> list[dict[str, Any]]:
    _require_data()
    return pipeline.headline_patterns(n)


@app.get("/api/alerts")
def alerts(limit: int = 12) -> list[dict[str, Any]]:
    """Most urgent SIF-potential reports for the dashboard alert panel."""
    _require_data()
    rows = [r for r in pipeline.dataset.records if r["is_sif"]]
    rows.sort(key=lambda r: (-r["risk_score"], -r["confidence"]))
    return rows[:limit]


@app.get("/api/validation")
def validation() -> dict[str, Any]:
    _require_data()
    return pipeline.validation()


@app.get("/api/review-queue")
def review_queue(limit: int = 100) -> dict[str, Any]:
    _require_data()
    return {
        "notice": DECISION_SUPPORT_NOTICE,
        "items": pipeline.review_queue(limit),
    }


# --------------------------------------------------------------------------
# Ad-hoc analysis
# --------------------------------------------------------------------------


class AnalyseRequest(BaseModel):
    narrative: str = Field(..., min_length=10, max_length=8000)


@app.post("/api/analyse")
def analyse_text(req: AnalyseRequest) -> dict[str, Any]:
    """Analyse a single pasted narrative - the live demo endpoint."""
    return pipeline.analyse_text(req.narrative)


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------


@app.post("/api/upload", dependencies=[Depends(require_write_access)])
async def upload(
    file: UploadFile = File(...),
    is_demo: bool = Query(
        True,
        description="Set false ONLY for genuine operational data; controls the demo banner.",
    ),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds the 100 MB limit.")

    try:
        ds = pipeline.load_csv(raw, file.filename, is_demo=is_demo)
    except DataLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to the UI
        raise HTTPException(status_code=500, detail=f"Could not analyse the file: {exc}")

    return {
        "ok": True,
        "dataset_name": ds.name,
        "rows_loaded": len(ds.records),
        "analysis_seconds": ds.analysis_seconds,
        "has_ground_truth": ds.has_ground_truth,
        "model_trained": ds.model_trained,
        "is_demo": ds.is_demo,
        **ds.load_info,
    }


@app.post("/api/reload-demo", dependencies=[Depends(require_write_access)])
def reload_demo() -> dict[str, Any]:
    if not DEMO_CSV.exists():
        raise HTTPException(status_code=404, detail="Demo corpus not found on disk.")
    ds = pipeline.load_path(DEMO_CSV, is_demo=True)
    return {"ok": True, "rows_loaded": len(ds.records), "dataset_name": ds.name}


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


class ThresholdUpdate(BaseModel):
    sif_confidence: float | None = Field(None, ge=0.0, le=1.0)
    review_low: float | None = Field(None, ge=0.0, le=1.0)
    review_high: float | None = Field(None, ge=0.0, le=1.0)
    risk_critical: float | None = Field(None, ge=0.0, le=1.0)
    risk_high: float | None = Field(None, ge=0.0, le=1.0)
    risk_medium: float | None = Field(None, ge=0.0, le=1.0)
    min_reports_for_ranking: int | None = Field(None, ge=1, le=1000)
    min_pattern_occurrences: int | None = Field(None, ge=2, le=100)


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    d = pipeline.dataset
    return {
        **pipeline.settings.as_dict(),
        "dataset": {
            "name": d.name,
            "rows": len(d.records),
            "loaded": d.loaded,
            "is_demo": d.is_demo,
            "has_ground_truth": d.has_ground_truth,
            "last_analysed": d.analysed_at,
            "analysis_seconds": d.analysis_seconds,
            "load_info": d.load_info,
        },
        "model": {
            "type": "TF-IDF (1-2 gram) + Logistic Regression, blended with an "
                    "energy/barrier rule score",
            "trained": d.model_trained,
            "outcome_masking": pipeline.classifier.mask_outcomes,
            "blend_model_weight": pipeline.classifier.blend_model,
            "metrics": d.model_metrics,
        },
        "notice": DECISION_SUPPORT_NOTICE,
        "tagline": TAGLINE,
        "write_protected": bool(ADMIN_TOKEN),
    }


@app.patch("/api/settings/thresholds", dependencies=[Depends(require_write_access)])
def update_thresholds(update: ThresholdUpdate) -> dict[str, Any]:
    """
    Retune thresholds and re-derive every dependent view.

    Re-runs the classification stage only. Extraction and rule mapping do not
    depend on thresholds, so a retune is fast even on a large dataset.
    """
    t = pipeline.settings.thresholds
    for key, value in update.model_dump(exclude_none=True).items():
        setattr(t, key, value)

    if t.review_low > t.review_high:
        t.review_low, t.review_high = t.review_high, t.review_low

    pipeline.classifier.threshold = t.sif_confidence

    if pipeline.dataset.loaded:
        from sif.risk_engine import needs_human_review, risk_level

        for r in pipeline.dataset.records:
            r["is_sif"] = r["confidence"] >= t.sif_confidence
            r["classification"] = "SIF-Potential" if r["is_sif"] else "Non-SIF-Potential"
            r["risk_level"] = risk_level(r["risk_score"], t)
            r["needs_review"], r["review_reason"] = needs_human_review(
                r["confidence"], r["risk_level"], r["status"], t
            )

    return {"ok": True, **pipeline.settings.as_dict()}


# --------------------------------------------------------------------------
# Serve the built frontend
#
# In development the Vite dev server proxies /api to this process. In a
# deployment there is no proxy, so the built bundle is served from here: one
# origin, one process, no CORS, and SPA deep links (/reports, /settings) resolve
# instead of 404ing on refresh.
#
#     cd frontend && npm run build
#     cd backend  && uvicorn main:app --port 8000
# --------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve real files when they exist; otherwise hand back index.html."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"No API route /{full_path}")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and FRONTEND_DIST.resolve() in candidate.parents
        ):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
