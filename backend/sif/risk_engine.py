"""
Risk scoring and site/activity ranking.

Two jobs:

  1. Composite risk for a single report - blending model confidence with the
     physical facts of the event, so ranking is not a popularity contest between
     well-written reports.

  2. SIF-precursor DENSITY ranking for sites and activities. The problem
     statement is explicit that density, not raw count, is the ranking metric:
     a site that files 400 reports will out-count a site that files 20 without
     being more dangerous. Density inverts that bias.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .config import RiskWeights, Thresholds
from .precursor_extractor import ExtractionResult


# --------------------------------------------------------------------------
# Per-report risk
# --------------------------------------------------------------------------


def composite_risk(
    confidence: float,
    extraction: ExtractionResult,
    weights: RiskWeights | None = None,
) -> float:
    """
    Blend model confidence with hazard energy, barrier failure and outcome.

    Deliberately not the model probability alone: a confidently-classified
    paper-cut must not outrank an ambiguous narrative about an unisolated
    high-voltage panel.
    """
    w = (weights or RiskWeights()).normalised()

    failed = extraction.failed_barriers
    barrier_component = (
        max(b.weight for b in failed) * min(1.0, 0.7 + 0.15 * (len(failed) - 1))
        if failed
        else 0.0
    )

    score = (
        w["model_confidence"] * float(confidence)
        + w["hazard_energy"] * extraction.max_hazard_weight
        + w["barrier_failure"] * barrier_component
        + w["outcome_severity"] * extraction.severity_score
    )
    return round(float(min(1.0, max(0.0, score))), 4)


def risk_level(score: float, t: Thresholds | None = None) -> str:
    t = t or Thresholds()
    if score >= t.risk_critical:
        return "Critical"
    if score >= t.risk_high:
        return "High"
    if score >= t.risk_medium:
        return "Medium"
    return "Low"


def density_level(density: float, t: Thresholds | None = None) -> str:
    """Absolute density banding. Used where no corpus baseline is available."""
    t = t or Thresholds()
    if density >= t.density_critical:
        return "Critical"
    if density >= t.density_high:
        return "High"
    if density >= t.density_medium:
        return "Medium"
    return "Low"


def _z_above_baseline(k: int, n: int, p0: float) -> float:
    """
    One-sided z score for "this group's SIF rate exceeds the corpus baseline".

    Normal approximation to the binomial. Guards against the small-sample trap
    that makes a site with 2 reports and 1 SIF look like a 50%-density crisis.
    """
    if n <= 0 or p0 <= 0 or p0 >= 1:
        return 0.0
    se = (p0 * (1 - p0) / n) ** 0.5
    if se == 0:
        return 0.0
    return ((k / n) - p0) / se


def relative_density_level(
    sif_count: int, total: int, baseline: float, t: Thresholds | None = None
) -> tuple[str, float, float]:
    """
    Band a group's SIF density RELATIVE to the corpus baseline.

    Absolute cut-offs cannot work across datasets: a 30% density is unremarkable
    in a corpus averaging 28% and alarming in one averaging 8%. Banding on the
    ratio to baseline - and requiring statistical significance before calling
    anything High or Critical - keeps the ranking meaningful whatever an operator
    uploads, and stops small sites being flagged on noise.

    Returns (level, ratio, z_score).
    """
    t = t or Thresholds()
    if total <= 0 or baseline <= 0:
        return "Low", 0.0, 0.0

    density = sif_count / total
    ratio = density / baseline
    z = _z_above_baseline(sif_count, total, baseline)
    significant = z >= 1.64  # one-sided, ~95%

    if ratio >= 1.40 and significant:
        return "Critical", ratio, z
    if ratio >= 1.15 and significant:
        return "High", ratio, z
    if ratio >= 1.0:
        return "Medium", ratio, z
    return "Low", ratio, z


def needs_human_review(
    confidence: float, risk: str, status: str, t: Thresholds | None = None
) -> tuple[bool, str]:
    """
    Route a report to the HSE review queue.

    Two independent triggers, per the spec:
      * the model is not confident enough to be trusted alone, or
      * the consequence is severe enough that a human must sign it off.
    """
    t = t or Thresholds()
    if status == "Reviewed":
        return False, ""
    if risk == "Critical":
        return True, "Critical risk - mandatory HSE verification"
    if t.review_low <= confidence <= t.review_high:
        return True, f"Model confidence {confidence:.0%} is within the uncertainty band"
    return False, ""


# --------------------------------------------------------------------------
# Aggregate ranking
# --------------------------------------------------------------------------


@dataclass
class GroupRisk:
    key: str
    total_reports: int
    sif_reports: int
    sif_density: float
    risk_level: str
    dominant_rule: str = "-"
    dominant_activity: str = "-"
    top_precursor: str = "-"
    avg_confidence: float = 0.0
    critical_reports: int = 0
    density_ratio: float = 1.0
    z_score: float = 0.0
    significant: bool = False
    ranked: bool = True
    suppressed_reason: str = ""
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "total_reports": self.total_reports,
            "sif_reports": self.sif_reports,
            "sif_density": round(self.sif_density, 4),
            "risk_level": self.risk_level,
            "dominant_rule": self.dominant_rule,
            "dominant_activity": self.dominant_activity,
            "top_precursor": self.top_precursor,
            "avg_confidence": round(self.avg_confidence, 4),
            "critical_reports": self.critical_reports,
            "density_ratio": round(self.density_ratio, 3),
            "z_score": round(self.z_score, 2),
            "significant": self.significant,
            "ranked": self.ranked,
            "suppressed_reason": self.suppressed_reason,
            "examples": self.examples,
        }


def _mode(values) -> str:
    vals = [v for v in values if v and v not in ("-", "Unclassified", "Unmapped")]
    return Counter(vals).most_common(1)[0][0] if vals else "-"


def rank_groups(
    records: list[dict],
    group_field: str,
    t: Thresholds | None = None,
) -> list[GroupRisk]:
    """
    Rank sites (or activities) by SIF-precursor density.

    Groups below `min_reports_for_ranking` are still returned but flagged
    `ranked=False`, so a location with 1 report and 1 SIF cannot claim a 100%
    density and top the table. They are shown separately rather than hidden,
    because a small site with a critical precursor still deserves attention.
    """
    t = t or Thresholds()
    buckets: dict[str, list[dict]] = {}
    for r in records:
        key = r.get(group_field) or "Unspecified"
        buckets.setdefault(key, []).append(r)

    # Corpus baseline that every group is judged against.
    baseline = (
        sum(1 for r in records if r.get("is_sif")) / len(records) if records else 0.0
    )

    out: list[GroupRisk] = []
    for key, rows in buckets.items():
        total = len(rows)
        sif_rows = [r for r in rows if r.get("is_sif")]
        n_sif = len(sif_rows)
        density = n_sif / total if total else 0.0
        ranked = total >= t.min_reports_for_ranking
        level, ratio, z = relative_density_level(n_sif, total, baseline, t)

        precursors: list[str] = []
        for r in sif_rows:
            precursors.extend(r.get("failed_barriers") or [])

        out.append(
            GroupRisk(
                key=key,
                total_reports=total,
                sif_reports=n_sif,
                sif_density=density,
                risk_level=level if ranked else "Unranked",
                density_ratio=ratio,
                z_score=z,
                significant=bool(z >= 1.64) and ranked,
                dominant_rule=_mode(r.get("iogp_rule_name") for r in sif_rows),
                dominant_activity=_mode(r.get("activity") for r in sif_rows),
                top_precursor=_mode(precursors),
                avg_confidence=(
                    sum(r.get("confidence", 0) for r in sif_rows) / n_sif if n_sif else 0.0
                ),
                critical_reports=sum(1 for r in rows if r.get("risk_level") == "Critical"),
                ranked=ranked,
                suppressed_reason=(
                    ""
                    if ranked
                    else f"Only {total} report(s); minimum {t.min_reports_for_ranking} required for density ranking"
                ),
                examples=[r.get("report_id", "") for r in sif_rows[:3]],
            )
        )

    # Ranked groups first, by density; unranked appended by raw SIF count.
    out.sort(key=lambda g: (not g.ranked, -g.sif_density, -g.sif_reports))
    return out


def ranking_baseline(records: list[dict]) -> float:
    """Corpus-wide SIF density that group rankings are measured against."""
    return (
        sum(1 for r in records if r.get("is_sif")) / len(records) if records else 0.0
    )
