"""
End-to-end analysis pipeline.

    CSV -> load -> preprocess -> extract -> classify -> map -> risk
        -> patterns -> rankings -> in-memory analysed frame

Holds the analysed dataset in memory and serves every dashboard view from it, so
the expensive work happens once per upload rather than once per request.
"""

from __future__ import annotations

import hashlib
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import knowledge as kb
from .config import DEMO_BANNER, Settings, Thresholds
from .data_loader import LoadResult, load
from .iogp_mapper import map_rule
from .pattern_detector import detect_patterns, top_patterns
from .precursor_extractor import extract
from .risk_engine import composite_risk, needs_human_review, rank_groups, risk_level
from .sif_classifier import SIFClassifier


@dataclass
class Dataset:
    """One loaded, fully analysed dataset."""

    name: str = "No dataset loaded"
    records: list[dict] = field(default_factory=list)
    frame: pd.DataFrame | None = None
    load_info: dict = field(default_factory=dict)
    is_demo: bool = True
    has_ground_truth: bool = False
    analysed_at: float = 0.0
    analysis_seconds: float = 0.0
    model_trained: bool = False
    model_metrics: dict = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return bool(self.records)


class Pipeline:
    """Owns the classifier and the currently loaded dataset."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.classifier = SIFClassifier(threshold=self.settings.thresholds.sif_confidence)
        self.dataset = Dataset()

    # -- analysis cache ---------------------------------------------------
    #
    # Full analysis of the demo corpus takes ~28s. On a hosted free tier that
    # exceeds the platform health-check window and the service is killed before
    # it ever answers. Caching the analysed result cuts cold start to ~2s.
    #
    # The cache key includes the source file's size+mtime AND a fingerprint of
    # the knowledge base, so editing a rule or a threshold invalidates it rather
    # than silently serving stale analysis.
    CACHE_VERSION = 3

    @staticmethod
    def _kb_fingerprint() -> str:
        src = Path(__file__).parent
        h = hashlib.sha256()
        for name in ("knowledge.py", "precursor_extractor.py", "sif_classifier.py",
                     "iogp_mapper.py", "risk_engine.py"):
            f = src / name
            if f.exists():
                h.update(f.read_bytes())
        return h.hexdigest()[:16]

    def _cache_path(self, csv_path: Path) -> Path:
        stat = csv_path.stat()
        key = f"{csv_path.name}:{stat.st_size}:{int(stat.st_mtime)}:{self._kb_fingerprint()}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:20]
        cache_dir = Path(__file__).resolve().parents[2] / "models" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"analysis-v{self.CACHE_VERSION}-{digest}.pkl"

    def load_path_cached(self, path: str | Path, is_demo: bool = True) -> Dataset:
        """Load from cache when the CSV and engine are both unchanged."""
        path = Path(path)
        cache = self._cache_path(path)

        if cache.exists():
            try:
                with cache.open("rb") as fh:
                    blob = pickle.load(fh)
                self.classifier = blob["classifier"]
                self.dataset = blob["dataset"]
                self.settings.dataset_name = self.dataset.name
                self.settings.demo_mode = self.dataset.is_demo
                self.dataset.frame = None  # frame is not needed for serving
                return self.dataset
            except Exception:
                # A corrupt or version-mismatched cache must never block startup.
                try:
                    cache.unlink()
                except OSError:
                    pass

        ds = self.load_path(path, is_demo=is_demo)
        try:
            payload = {"classifier": self.classifier, "dataset": ds}
            ds_frame, ds.frame = ds.frame, None      # do not pickle the raw frame
            with cache.open("wb") as fh:
                pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
            ds.frame = ds_frame
        except Exception:
            pass  # caching is an optimisation, never a requirement
        return ds

    # -- ingestion --------------------------------------------------------
    def load_csv(self, source, filename: str = "uploaded.csv",
                 override: dict[str, str] | None = None,
                 is_demo: bool = True) -> Dataset:
        res: LoadResult = load(source, filename, override)
        return self.analyse(res, filename, is_demo)

    def load_path(self, path: str | Path, is_demo: bool = True) -> Dataset:
        path = Path(path)
        return self.load_csv(path, path.name, is_demo=is_demo)

    # -- analysis ---------------------------------------------------------
    def analyse(self, res: LoadResult, name: str, is_demo: bool = True) -> Dataset:
        t0 = time.perf_counter()
        df = res.frame
        narratives = df["narrative"].tolist()

        # 1. Concept extraction (activity, hazard, barrier status).
        extractions = [extract(n) for n in narratives]

        # 2. Train on ground truth when the dataset carries verified labels.
        #
        # Synthetic rows are EXCLUDED from both training and metrics. Their
        # labels are true by construction (we wrote the templates), so training
        # on them would let the model learn template artefacts - the generated
        # closing sentence differs between the SIF and non-SIF templates - and
        # any metric computed on them would be self-congratulatory.
        # They are still classified at inference like any other report.
        labels = df["sif_label"]
        trainable = labels.notna()
        if "narrative_provenance" in df.columns:
            synthetic = df["narrative_provenance"].astype(str).eq("synthetic")
            trainable &= ~synthetic
        else:
            synthetic = pd.Series(False, index=df.index)

        has_truth = bool(trainable.sum() >= 50 and labels[trainable].nunique() > 1)
        metrics: dict = {}
        if has_truth:
            metrics = self._train(
                [n for n, m in zip(narratives, trainable) if m],
                labels[trainable].astype(int).tolist(),
            )
            metrics["excluded_synthetic_rows"] = int(synthetic.sum())
            metrics["trained_on"] = (
                "real narratives only; synthetic observations excluded from "
                "training and metrics"
            )

        # 3. Classification.
        results = self.classifier.predict_batch(narratives, extractions)

        # 4. Rule mapping, risk, assembly.
        t = self.settings.thresholds
        records: list[dict] = []
        for i, (row, ex, cls) in enumerate(zip(df.to_dict("records"), extractions, results)):
            rm = map_rule(narratives[i], ex)
            risk = composite_risk(cls.confidence, ex, self.settings.risk_weights)
            rlevel = risk_level(risk, t)
            status = row.get("status") or "Pending Review"
            review, reason = needs_human_review(cls.confidence, rlevel, status, t)

            date_val = row.get("date")
            records.append(
                {
                    "report_id": row.get("report_id"),
                    "date": None if pd.isna(date_val) else pd.Timestamp(date_val).date().isoformat(),
                    "location": row.get("location") or "Unspecified",
                    "asset": row.get("asset") or "Unspecified",
                    "report_type": row.get("report_type") or "Unspecified",
                    "narrative": row.get("narrative"),
                    "status": status,
                    # classification
                    "is_sif": bool(cls.is_sif),
                    "classification": cls.label,
                    "confidence": cls.confidence,
                    "model_probability": None if cls.model_probability != cls.model_probability
                                          else cls.model_probability,
                    "rule_probability": cls.rule_probability,
                    # extraction
                    "activity": ex.primary_activity,
                    "activities": ex.activity_labels,
                    "hazard": ex.primary_hazard if ex.hazards else (
                        kb.HAZARDS[ex.implied_hazards[0]]["label"] if ex.implied_hazards
                        else "Unclassified"),
                    "hazard_is_implied": not ex.hazards and bool(ex.implied_hazards),
                    "exposure": ex.exposure,
                    "precursors": ex.precursor_labels(),
                    "failed_barriers": ex.failed_barrier_labels,
                    "present_barriers": [b.label for b in ex.present_barriers],
                    "barrier_evidence": [
                        {"barrier": b.label, "status": b.status, "evidence": b.evidence}
                        for b in ex.barriers
                    ],
                    # mapping
                    "iogp_rule": rm.rule,
                    "iogp_rule_name": rm.rule_name,
                    "iogp_explanation": rm.explain(),
                    "iogp_secondary": rm.secondary_rules,
                    # risk
                    "risk_score": risk,
                    "risk_level": rlevel,
                    "needs_review": review,
                    "review_reason": reason,
                    # ground truth, when present
                    "sif_label": None if pd.isna(row.get("sif_label")) else int(row["sif_label"]),
                    "sector_provenance": row.get("sector_provenance"),
                    "narrative_provenance": row.get("narrative_provenance"),
                }
            )

        self.dataset = Dataset(
            name=name,
            records=records,
            frame=df,
            load_info=res.as_dict(),
            is_demo=is_demo,
            has_ground_truth=has_truth,
            analysed_at=time.time(),
            analysis_seconds=round(time.perf_counter() - t0, 2),
            model_trained=self.classifier.is_fitted,
            model_metrics=metrics,
        )
        self.settings.dataset_name = name
        self.settings.demo_mode = is_demo
        return self.dataset

    # -- training + validation -------------------------------------------
    def _train(self, narratives: list[str], labels: list[int]) -> dict:
        """
        Train on a held-out split and report metrics measured on unseen data.

        Metrics come from the test split only. Reporting training-set numbers
        would flatter the model and mislead the HSE team reading them.
        """
        from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                     precision_score, recall_score, roc_auc_score)
        from sklearn.model_selection import train_test_split

        Xtr, Xte, ytr, yte = train_test_split(
            narratives, labels, test_size=0.25, random_state=42, stratify=labels
        )
        self.classifier.fit(Xtr, ytr)

        proba = self.classifier._model_proba(Xte)
        pred = (proba >= self.settings.thresholds.sif_confidence).astype(int)
        tn, fp, fn, tp = confusion_matrix(yte, pred, labels=[0, 1]).ravel()

        # Refit on everything so inference uses all available signal.
        self.classifier.fit(narratives, labels)

        return {
            "accuracy": round(float(accuracy_score(yte, pred)), 4),
            "precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(yte, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(yte, proba)), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "train_size": len(Xtr),
            "test_size": len(Xte),
            "evaluated_on": "held-out test split (25%), never seen during training",
            "outcome_masking": self.classifier.mask_outcomes,
        }

    # -- views ------------------------------------------------------------
    @property
    def t(self) -> Thresholds:
        return self.settings.thresholds

    def kpis(self) -> dict:
        recs = self.dataset.records
        total = len(recs)
        if not total:
            return {"loaded": False, "banner": DEMO_BANNER}

        sif = [r for r in recs if r["is_sif"]]
        sites = rank_groups(recs, "location", self.t)
        ranked_sites = [s for s in sites if s.ranked]
        rules = [r["iogp_rule_name"] for r in sif if r["iogp_rule_name"] != "Unmapped"]
        pats = detect_patterns(recs, self.t)

        from collections import Counter
        return {
            "loaded": True,
            "is_demo": self.dataset.is_demo,
            "banner": DEMO_BANNER if self.dataset.is_demo else "",
            "dataset_name": self.dataset.name,
            "total_reports": total,
            "sif_reports": len(sif),
            "sif_density": round(len(sif) / total, 4),
            "high_risk_sites": sum(
                1 for s in ranked_sites if s.risk_level in ("Critical", "High")
            ),
            "awaiting_review": sum(1 for r in recs if r["needs_review"]),
            "high_confidence_alerts": sum(
                1 for r in sif if r["confidence"] >= self.t.review_high
            ),
            "most_frequent_rule": Counter(rules).most_common(1)[0][0] if rules else "-",
            "critical_patterns": sum(
                1 for p in pats if p.risk_level in ("Critical", "High")
            ),
            "critical_reports": sum(1 for r in recs if r["risk_level"] == "Critical"),
            "analysis_seconds": self.dataset.analysis_seconds,
        }

    def site_ranking(self) -> list[dict]:
        return [g.as_dict() for g in rank_groups(self.dataset.records, "location", self.t)]

    def activity_ranking(self) -> list[dict]:
        return [g.as_dict() for g in rank_groups(self.dataset.records, "activity", self.t)]

    def rule_distribution(self) -> list[dict]:
        recs = self.dataset.records
        out = []
        for key, spec in kb.IOGP_RULES.items():
            rows = [r for r in recs if r["iogp_rule"] == key]
            sif_rows = [r for r in rows if r["is_sif"]]
            precursors = [b for r in sif_rows for b in r["failed_barriers"]]
            from collections import Counter
            out.append(
                {
                    "rule": key,
                    "name": spec["name"],
                    "icon": spec["icon"],
                    "statement": spec["statement"],
                    "description": spec["description"],
                    "total_reports": len(rows),
                    "sif_reports": len(sif_rows),
                    "sif_density": round(len(sif_rows) / len(rows), 4) if rows else 0.0,
                    "top_precursor": Counter(precursors).most_common(1)[0][0] if precursors else "-",
                    "examples": [
                        {"report_id": r["report_id"], "narrative": r["narrative"][:220],
                         "confidence": r["confidence"], "location": r["location"]}
                        for r in sorted(sif_rows, key=lambda x: -x["confidence"])[:3]
                    ],
                }
            )
        out.sort(key=lambda x: -x["total_reports"])
        return out

    def patterns(self, limit: int = 40) -> list[dict]:
        return [p.as_dict() for p in detect_patterns(self.dataset.records, self.t)[:limit]]

    def headline_patterns(self, n: int = 8) -> list[dict]:
        return [p.as_dict() for p in top_patterns(self.dataset.records, self.t, n)]

    def review_queue(self, limit: int = 100) -> list[dict]:
        rows = [r for r in self.dataset.records if r["needs_review"]]
        rows.sort(key=lambda r: (-r["risk_score"], -r["confidence"]))
        return rows[:limit]

    def validation(self) -> dict:
        """
        Validation metrics, or an honest statement that they are unavailable.

        Never invents numbers: with no verified labels the UI must say so and
        explain what production validation would require.
        """
        d = self.dataset
        if not d.has_ground_truth:
            return {
                "available": False,
                "message": "Validation dataset not yet available",
                "explanation": (
                    "No verified SIF labels were found in the loaded dataset, so accuracy, "
                    "precision, recall and F1 cannot be calculated. Production validation "
                    "requires a sample of reports independently classified by qualified HSE "
                    "professionals - typically 300-500 reports, dual-reviewed with "
                    "disagreements adjudicated, covering every Life-Saving Rule and both "
                    "SIF and non-SIF outcomes."
                ),
                "reviewed_reports": sum(1 for r in d.records if r["status"] == "Reviewed"),
                "review_queue_size": sum(1 for r in d.records if r["needs_review"]),
            }
        return {
            "available": True,
            "reviewed_reports": int(sum(1 for r in d.records if r["sif_label"] is not None)),
            "review_queue_size": sum(1 for r in d.records if r["needs_review"]),
            **d.model_metrics,
        }

    def get_report(self, report_id: str) -> dict | None:
        return next((r for r in self.dataset.records if r["report_id"] == report_id), None)

    def analyse_text(self, narrative: str) -> dict:
        """Ad-hoc analysis of a single pasted narrative."""
        ex = extract(narrative)
        cls = self.classifier.predict_one(narrative, ex)
        rm = map_rule(narrative, ex)
        risk = composite_risk(cls.confidence, ex, self.settings.risk_weights)
        rlevel = risk_level(risk, self.t)
        review, reason = needs_human_review(cls.confidence, rlevel, "Pending Review", self.t)
        return {
            "narrative": narrative,
            "classification": cls.label,
            "is_sif": cls.is_sif,
            "confidence": cls.confidence,
            "model_probability": None if cls.model_probability != cls.model_probability
                                  else cls.model_probability,
            "rule_probability": cls.rule_probability,
            "activity": ex.primary_activity,
            "hazard": ex.primary_hazard if ex.hazards else (
                kb.HAZARDS[ex.implied_hazards[0]]["label"] if ex.implied_hazards else "Unclassified"),
            "exposure": ex.exposure,
            "precursors": ex.precursor_labels(),
            "failed_barriers": ex.failed_barrier_labels,
            "present_barriers": [b.label for b in ex.present_barriers],
            "barrier_evidence": [
                {"barrier": b.label, "status": b.status, "evidence": b.evidence}
                for b in ex.barriers
            ],
            "iogp_rule": rm.rule,
            "iogp_rule_name": rm.rule_name,
            "iogp_explanation": rm.explain(),
            "risk_score": risk,
            "risk_level": rlevel,
            "needs_review": review,
            "review_reason": reason,
            "recommended_action": (
                "HSE verification required" if review or cls.is_sif
                else "Routine tracking"
            ),
        }
