"""
Recurring precursor pattern detection.

The spec calls this one of the most important parts of the project, and it is
where the system stops being a classifier and starts being an intelligence tool.
Classifying one report tells an HSE manager about one report. Telling them that
"Hot Work without Fire Watch" has now occurred 14 times across 4 locations tells
them where to send an intervention.

Normalisation
-------------
The same barrier failure is written a dozen ways in the field:

    "fire watcher absent" / "no fire watch" / "fire watch not available"
    / "firewatch missing"

All of these already collapse to one canonical concept upstream, in
`knowledge.canonical_barrier_failure`, because the extractor resolves a barrier
KEY plus a STATUS rather than matching surface strings. Pattern mining therefore
operates on concepts, not phrases, and no fuzzy string clustering is needed.

Pattern families
----------------
Four combinations are mined, coarse to specific:

    rule + barrier                       "Hot Work / Fire Watch Missing"
    activity + barrier                   "Welding / Fire Watch Missing"
    activity + location + barrier        "Welding / Moran / Fire Watch Missing"
    hazard + activity + location         "Flammable Release / Welding / Moran"

Only combinations recurring at least `min_pattern_occurrences` times are
reported, so a single odd report never becomes a "pattern".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import Thresholds
from .risk_engine import density_level


@dataclass
class Pattern:
    pattern_id: str
    family: str
    label: str
    components: dict[str, str]
    occurrences: int
    sif_occurrences: int
    sites: list[str] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    avg_confidence: float = 0.0
    max_risk: str = "Low"
    risk_level: str = "Low"
    example_reports: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "family": self.family,
            "label": self.label,
            "components": self.components,
            "occurrences": self.occurrences,
            "sif_occurrences": self.sif_occurrences,
            "sites": self.sites,
            "site_count": len(self.sites),
            "activities": self.activities,
            "rules": self.rules,
            "avg_confidence": round(self.avg_confidence, 4),
            "max_risk": self.max_risk,
            "risk_level": self.risk_level,
            "example_reports": self.example_reports,
        }


_RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _combos(rec: dict) -> list[tuple[str, str, dict[str, str]]]:
    """Every (family, label, components) this record contributes to."""
    out: list[tuple[str, str, dict[str, str]]] = []
    rule = rec.get("iogp_rule_name") or ""
    activity = rec.get("activity") or ""
    location = rec.get("location") or ""
    hazard = rec.get("hazard") or ""
    barriers = rec.get("failed_barriers") or []

    for b in barriers:
        if rule and rule != "Unmapped":
            out.append(("rule_barrier", f"{rule} - {b}", {"rule": rule, "barrier": b}))
        if activity and activity != "Unclassified":
            out.append(
                ("activity_barrier", f"{activity} - {b}", {"activity": activity, "barrier": b})
            )
            if location:
                out.append(
                    (
                        "activity_location_barrier",
                        f"{activity} at {location} - {b}",
                        {"activity": activity, "location": location, "barrier": b},
                    )
                )

    if hazard and hazard != "Unclassified" and activity and activity != "Unclassified" and location:
        out.append(
            (
                "hazard_activity_location",
                f"{hazard} during {activity} at {location}",
                {"hazard": hazard, "activity": activity, "location": location},
            )
        )
    return out


def detect_patterns(
    records: list[dict],
    t: Thresholds | None = None,
    sif_only: bool = True,
) -> list[Pattern]:
    """
    Mine recurring precursor combinations.

    `sif_only` restricts mining to SIF-potential reports, which is the intended
    behaviour: a recurring combination of controls that held is good news, not a
    precursor pattern.
    """
    t = t or Thresholds()
    pool = [r for r in records if r.get("is_sif")] if sif_only else list(records)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    comp_map: dict[tuple[str, str], dict[str, str]] = {}
    for rec in pool:
        for family, label, components in _combos(rec):
            key = (family, label)
            groups[key].append(rec)
            comp_map.setdefault(key, components)

    patterns: list[Pattern] = []
    for (family, label), rows in groups.items():
        if len(rows) < t.min_pattern_occurrences:
            continue

        sites = sorted({r.get("location") for r in rows if r.get("location")})
        activities = sorted({r.get("activity") for r in rows if r.get("activity")})
        rules = sorted({r.get("iogp_rule_name") for r in rows if r.get("iogp_rule_name")})
        confidences = [r.get("confidence", 0.0) for r in rows]
        max_risk = max(
            (r.get("risk_level", "Low") for r in rows),
            key=lambda x: _RISK_ORDER.get(x, 0),
            default="Low",
        )
        n_sif = sum(1 for r in rows if r.get("is_sif"))

        patterns.append(
            Pattern(
                pattern_id=f"{family}:{abs(hash(label)) % 10**8}",
                family=family,
                label=label,
                components=comp_map[(family, label)],
                occurrences=len(rows),
                sif_occurrences=n_sif,
                sites=sites,
                activities=activities,
                rules=rules,
                avg_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
                max_risk=max_risk,
                risk_level=density_level(n_sif / len(rows), t) if rows else "Low",
                example_reports=[
                    {
                        "report_id": r.get("report_id"),
                        "location": r.get("location"),
                        "date": r.get("date"),
                        "narrative": (r.get("narrative") or "")[:240],
                        "confidence": r.get("confidence"),
                    }
                    for r in sorted(rows, key=lambda x: -x.get("confidence", 0))[:3]
                ],
            )
        )

    # Rank by breadth first: a pattern spanning many sites is a systemic issue,
    # not a local one, and is what an HSE team most needs to see.
    patterns.sort(key=lambda p: (-len(p.sites), -p.occurrences, -p.avg_confidence))
    return patterns


def top_patterns(records: list[dict], t: Thresholds | None = None, n: int = 10) -> list[Pattern]:
    """Headline patterns for the dashboard, de-duplicated across families."""
    all_pats = detect_patterns(records, t)
    seen_barriers: set[str] = set()
    out: list[Pattern] = []

    # Prefer the most actionable family first, then fill.
    for family in (
        "rule_barrier",
        "activity_barrier",
        "activity_location_barrier",
        "hazard_activity_location",
    ):
        for p in all_pats:
            if p.family != family or len(out) >= n:
                continue
            sig = p.components.get("barrier") or p.components.get("hazard") or p.label
            if family == "rule_barrier" and sig in seen_barriers:
                continue
            seen_barriers.add(sig)
            out.append(p)
        if len(out) >= n:
            break
    return out[:n]
