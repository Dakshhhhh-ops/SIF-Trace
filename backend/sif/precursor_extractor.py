"""
Precursor, barrier and hazard extraction from free-text safety reports.

This module answers the question the whole project turns on:

    Was the critical control PRESENT and working, or was it MISSING, BYPASSED
    or APPLIED TOO LATE?

Why this is not keyword matching
--------------------------------
These two narratives share nearly all their vocabulary:

    A. "confined space permit was valid and gas testing was completed"
    B. "worker entered confined space without gas testing or permit"

A bag-of-words model sees the same tokens. The difference is entirely in the
grammatical relationship between the barrier term and the surrounding cue words.
So for every barrier mention we resolve a STATUS:

    FAILED   - absent, bypassed, expired, defeated, or performed too late
    PRESENT  - obtained, verified, valid, in place, completed
    UNKNOWN  - mentioned with no resolving context

Resolution uses four signals, in priority order:

    1. Ordering cues     "entered BEFORE gas testing was completed"  -> FAILED
    2. Negated presence  "permit was NOT valid"                      -> FAILED
    3. Failure cues      "WITHOUT gas testing"                       -> FAILED
    4. Presence cues     "gas testing was COMPLETED"                 -> PRESENT

Scoring is proximity-weighted within the clause, because a cue five characters
from the barrier term is far more likely to govern it than one fifty characters
away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from . import knowledge as kb
from .preprocessing import normalise_text, split_clauses

Status = Literal["FAILED", "PRESENT", "UNKNOWN"]

# --------------------------------------------------------------------------
# Pre-compiled pattern banks (compiled once at import; this module is hot)
# --------------------------------------------------------------------------


def _compile_any(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


_FAILURE_RE = _compile_any(kb.FAILURE_CUES)
_PRESENCE_RE = _compile_any(kb.PRESENCE_CUES)
_NEGATOR_RE = _compile_any(kb.PRESENCE_NEGATORS)

# "before"/"prior to" appearing to the LEFT of a barrier term means the work
# proceeded ahead of that control. Deliberately left-side only: "gas testing was
# completed before entry" is compliant and must not be flagged.
_ORDERING_RE = re.compile(
    r"\b(?:before|prior\s+to|ahead\s+of|without\s+waiting\s+for|in\s+advance\s+of)\b",
    re.IGNORECASE,
)

_BARRIER_RES: dict[str, re.Pattern] = {
    key: _compile_any(spec["triggers"]) for key, spec in kb.BARRIERS.items()
}
_HAZARD_RES: dict[str, re.Pattern] = {
    key: _compile_any(spec["patterns"]) for key, spec in kb.HAZARDS.items()
}
# Subset denoting an ACTUAL uncontrolled energy event rather than equipment or
# a location that merely implies potential.
_HAZARD_EVENT_RES: dict[str, re.Pattern] = {
    key: _compile_any(pats) for key, pats in kb.HAZARD_EVENT_PATTERNS.items()
}
_ACTIVITY_RES: dict[str, re.Pattern] = {
    key: _compile_any(spec["patterns"]) for key, spec in kb.ACTIVITIES.items()
}
_SEVERITY_RES: list[tuple[re.Pattern, float]] = [
    (re.compile(p, re.IGNORECASE), w) for p, w in kb.SEVERITY_CUES.items()
]

# Window sizes in characters, tuned on the OSHA/MSHA narrative style.
_LEFT_WINDOW = 60
_RIGHT_WINDOW = 45
_NEGATOR_WINDOW = 25


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------


@dataclass
class BarrierFinding:
    key: str
    label: str
    status: Status
    rule: str
    weight: float
    evidence: str
    canonical: str = ""

    def __post_init__(self) -> None:
        if not self.canonical and self.status == "FAILED":
            self.canonical = kb.canonical_barrier_failure(self.key)


@dataclass
class ExtractionResult:
    activities: list[str] = field(default_factory=list)
    activity_labels: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    hazard_labels: list[str] = field(default_factory=list)
    barriers: list[BarrierFinding] = field(default_factory=list)
    severity_score: float = 0.0
    severity_evidence: list[str] = field(default_factory=list)
    # Hazards not named in the text but implied by the activity. Tracked
    # separately so the UI can show which inferences were made rather than read.
    implied_hazards: list[str] = field(default_factory=list)
    # Hazards where an uncontrolled energy release actually occurred.
    hazard_events: list[str] = field(default_factory=list)

    # -- convenience views ------------------------------------------------
    @property
    def failed_barriers(self) -> list[BarrierFinding]:
        return [b for b in self.barriers if b.status == "FAILED"]

    @property
    def present_barriers(self) -> list[BarrierFinding]:
        return [b for b in self.barriers if b.status == "PRESENT"]

    @property
    def failed_barrier_labels(self) -> list[str]:
        return [b.canonical for b in self.failed_barriers]

    @property
    def primary_activity(self) -> str:
        return self.activity_labels[0] if self.activity_labels else "Unclassified"

    @property
    def primary_hazard(self) -> str:
        return self.hazard_labels[0] if self.hazard_labels else "Unclassified"

    @property
    def exposure(self) -> str:
        """How the person was exposed, derived from the primary activity."""
        if not self.activities:
            return "Exposure not determinable from narrative"
        return kb.EXPOSURE_TEMPLATES.get(
            self.activities[0], "Exposure not determinable from narrative"
        )

    @property
    def max_hazard_weight(self) -> float:
        """
        Strongest hazard weight. Stated hazards count fully; hazards merely
        implied by the activity are discounted, since inference is weaker
        evidence than the reporter naming the energy source outright.
        """
        stated = max((kb.HAZARDS[h]["sif_weight"] for h in self.hazards), default=0.0)
        implied = max(
            (kb.HAZARDS[h]["sif_weight"] * 0.8 for h in self.implied_hazards), default=0.0
        )
        return max(stated, implied)

    def precursor_labels(self) -> list[str]:
        """
        The human-readable precursor list shown in the report analysis view.

        A precursor is the combination of an exposure that exists and a control
        that did not hold - so it is built from hazards plus failed barriers,
        never from the presence of a keyword alone.
        """
        out: list[str] = []

        # An uncontrolled energy EVENT is a precursor in its own right: a gas
        # release or a dropped object means energy escaped, whatever the
        # paperwork says.
        #
        # Merely naming a hazard context is not enough. "Scaffold handrail was
        # installed and inspected" mentions a fall hazard, but nothing escaped
        # and every control held - flagging it would be a false alarm.
        for h in self.hazard_events:
            out.append(f"{kb.HAZARDS[h]['label']} exposure")

        # A hazard only INFERRED from the activity is routine work, not a
        # precursor - unless a control also failed. Confined-space entry with a
        # valid permit and a completed gas test is a job done properly, and must
        # never be surfaced as a precursor.
        if self.failed_barriers:
            for h in self.hazards:
                if h not in self.hazard_events:
                    out.append(f"{kb.HAZARDS[h]['label']} exposure")
            for h in self.implied_hazards:
                out.append(f"{kb.HAZARDS[h]['label']} exposure (implied by activity)")

        for b in self.failed_barriers:
            out.append(b.canonical)
        # De-duplicate, preserve order
        seen: set[str] = set()
        return [x for x in out if not (x in seen or seen.add(x))]


# --------------------------------------------------------------------------
# Barrier status resolution
# --------------------------------------------------------------------------


def _proximity_weight(distance: int, window: int) -> float:
    """Linear decay: a cue adjacent to the term counts ~1.0, at the edge ~0.2."""
    if distance < 0 or distance > window:
        return 0.0
    return 1.0 - 0.8 * (distance / window)


def _presence_is_negated(clause: str, presence_start: int) -> bool:
    """True when a negator immediately precedes a presence cue ("not completed")."""
    left = clause[max(0, presence_start - _NEGATOR_WINDOW) : presence_start]
    return bool(_NEGATOR_RE.search(left))


def resolve_barrier_status(clause: str, start: int, end: int) -> tuple[Status, str]:
    """
    Decide whether the barrier mentioned at [start:end] in `clause` held or failed.

    Returns (status, evidence_snippet).
    """
    left = clause[max(0, start - _LEFT_WINDOW) : start]
    right = clause[end : end + _RIGHT_WINDOW]

    failure_score = 0.0
    presence_score = 0.0
    evidence = ""

    # 1. Ordering cue on the left - work proceeded ahead of the control.
    for m in _ORDERING_RE.finditer(left):
        dist = len(left) - m.end()
        w = _proximity_weight(dist, _LEFT_WINDOW) * 1.15
        if w > failure_score:
            failure_score, evidence = w, m.group(0)

    # 2/3. Failure cues either side.
    for m in _FAILURE_RE.finditer(left):
        w = _proximity_weight(len(left) - m.end(), _LEFT_WINDOW)
        if w > failure_score:
            failure_score, evidence = w, m.group(0)
    for m in _FAILURE_RE.finditer(right):
        w = _proximity_weight(m.start(), _RIGHT_WINDOW) * 0.9
        if w > failure_score:
            failure_score, evidence = w, m.group(0)

    # 4. Presence cues - but a negated presence cue is really a failure.
    for m in _PRESENCE_RE.finditer(right):
        w = _proximity_weight(m.start(), _RIGHT_WINDOW)
        if _presence_is_negated(clause, end + m.start()):
            if w * 1.1 > failure_score:
                failure_score, evidence = w * 1.1, f"not {m.group(0)}"
        elif w > presence_score:
            presence_score, evidence = w, m.group(0)
    for m in _PRESENCE_RE.finditer(left):
        w = _proximity_weight(len(left) - m.end(), _LEFT_WINDOW) * 0.85
        if _presence_is_negated(left, m.start()):
            if w * 1.1 > failure_score:
                failure_score, evidence = w * 1.1, f"not {m.group(0)}"
        elif w > presence_score:
            presence_score, evidence = w, m.group(0)

    if failure_score >= presence_score and failure_score > 0.15:
        return "FAILED", evidence
    if presence_score > 0.15:
        return "PRESENT", evidence
    return "UNKNOWN", ""


# --------------------------------------------------------------------------
# Main extraction entry point
# --------------------------------------------------------------------------


def extract(narrative: str) -> ExtractionResult:
    """Run the full concept extraction over one free-text narrative."""
    result = ExtractionResult()
    if not narrative:
        return result

    text = normalise_text(narrative)
    if not text:
        return result

    # -- activities ------------------------------------------------------
    for key, rx in _ACTIVITY_RES.items():
        if rx.search(text):
            result.activities.append(key)
            result.activity_labels.append(kb.ACTIVITIES[key]["label"])

    # -- hazards ---------------------------------------------------------
    for key, rx in _HAZARD_RES.items():
        if rx.search(text):
            result.hazards.append(key)
            result.hazard_labels.append(kb.HAZARDS[key]["label"])
            ev = _HAZARD_EVENT_RES.get(key)
            if ev is not None and ev.search(text):
                result.hazard_events.append(key)
    # Strongest hazard first so primary_hazard is the most consequential one.
    order = sorted(
        range(len(result.hazards)),
        key=lambda i: kb.HAZARDS[result.hazards[i]]["sif_weight"],
        reverse=True,
    )
    result.hazards = [result.hazards[i] for i in order]
    result.hazard_labels = [result.hazard_labels[i] for i in order]

    # Hazards the activity implies but the reporter never spelled out. A confined
    # space entry carries an atmospheric hazard whether or not the word "toxic"
    # appears; recording it keeps the fatal-potential reasoning complete.
    for act in result.activities:
        for hz in kb.ACTIVITY_IMPLIED_HAZARDS.get(act, []):
            if hz not in result.hazards and hz not in result.implied_hazards:
                result.implied_hazards.append(hz)

    # -- barriers, resolved clause by clause -----------------------------
    # A barrier can be mentioned more than once; FAILED anywhere wins, because a
    # control that held at one step and failed at another is still a breach.
    best: dict[str, BarrierFinding] = {}
    rank = {"FAILED": 2, "PRESENT": 1, "UNKNOWN": 0}

    for clause in split_clauses(text):
        for key, rx in _BARRIER_RES.items():
            for m in rx.finditer(clause):
                status, evidence = resolve_barrier_status(clause, m.start(), m.end())
                if status == "UNKNOWN":
                    continue
                spec = kb.BARRIERS[key]
                finding = BarrierFinding(
                    key=key,
                    label=spec["label"],
                    status=status,
                    rule=spec["rule"],
                    weight=spec["weight"],
                    evidence=_snippet(clause, m.start(), m.end(), evidence),
                )
                prev = best.get(key)
                if prev is None or rank[status] > rank[prev.status]:
                    best[key] = finding
                break  # one resolution per barrier per clause is enough

    result.barriers = sorted(
        best.values(), key=lambda b: (b.status != "FAILED", -b.weight)
    )

    # -- outcome severity -------------------------------------------------
    for rx, weight in _SEVERITY_RES:
        m = rx.search(text)
        if m:
            result.severity_evidence.append(m.group(0))
            result.severity_score = max(result.severity_score, weight)

    return result


def _snippet(clause: str, start: int, end: int, cue: str) -> str:
    """Short quoted evidence for the UI, showing the barrier term in context."""
    lo = max(0, start - 45)
    hi = min(len(clause), end + 45)
    frag = clause[lo:hi].strip()
    prefix = "..." if lo > 0 else ""
    suffix = "..." if hi < len(clause) else ""
    return f"{prefix}{frag}{suffix}"
