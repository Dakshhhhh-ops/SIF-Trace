"""
Map a safety report to the relevant IOGP Life-Saving Rule.

Kept deliberately separate from classification so HSE teams can tune the mapping
without touching the model, as the spec requires.

Scoring
-------
Evidence is accumulated per rule from four independent channels, strongest first:

    failed barrier  0.55  - the control that broke points at the rule it protects
    stated hazard   0.40  - a named energy source implies its governing rule
    activity        0.30  - the work being done implies a rule
    direct phrase   0.45  - explicit rule language in the narrative
    implied hazard  0.15  - inferred, so weighted lowest

Every contribution is recorded, so the UI can explain WHY a rule was chosen in
language an HSE professional can audit and overrule. A report with no evidence
returns `None` rather than a guess - silence is more useful than a false mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import knowledge as kb
from .precursor_extractor import ExtractionResult
from .preprocessing import normalise_text

# Activity -> rule most often engaged by that activity.
ACTIVITY_RULE: dict[str, str] = {
    "confined_space_entry": "confined_space",
    "hot_work": "hot_work",
    "drilling": "line_of_fire",
    "workover": "line_of_fire",
    "maintenance": "energy_isolation",
    "lifting": "safe_mechanical_lifting",
    "working_at_height": "working_at_height",
    "electrical_work": "energy_isolation",
    "excavation": "confined_space",
    "transport": "driving",
    "production_ops": "energy_isolation",
    "inspection": "work_authorisation",
}

# Unambiguous rule language. These are phrases that name the rule's subject
# matter directly rather than merely hinting at it.
DIRECT_RULE_PATTERNS: dict[str, list[str]] = {
    "bypassing_safety_controls": [
        r"bypass\w*\s+(?:the\s+)?(?:safety|interlock|trip|alarm|guard|esd)",
        r"(?:interlock|trip|alarm|esd|safety\s+device|guard)s?\s+(?:was|were|been)?\s*(?:bypass|overrid|defeat|disabl|deactivat|jump)\w*",
        r"overrid\w*\s+(?:the\s+)?(?:safety|interlock|trip|alarm|protection)",
        r"defeat\w*\s+(?:the\s+)?(?:safety|interlock|guard)",
        r"safety\s+(?:system|device|control)s?\s+disabled",
    ],
    "confined_space": [
        r"confined\s+space",
        r"enter(?:ed|ing)?\s+(?:the\s+)?(?:vessel|tank|pit|sump|silo|man-?hole)",
        r"vessel\s+entry",
        r"oxygen\s+deficien\w*",
        r"tank\s+entry",
    ],
    "driving": [
        r"(?:vehicle|truck|car|bus)\s+(?:collision|accident|rollover|roll-?over|overturn)",
        r"road\s+traffic",
        r"speeding",
        r"seat-?belt",
        r"driving\s+(?:without|too\s+fast|unsafely)",
        r"lost\s+control\s+of\s+(?:the\s+)?vehicle",
    ],
    "energy_isolation": [
        r"(?:not|without|failed\s+to)\s+isolat\w*",
        r"isolation\s+(?:was\s+)?(?:not|never|missing|failed|bypassed)",
        r"lock\s+out\s+tag\s+out",
        r"zero\s+energy",
        r"live\s+(?:equipment|circuit|line|conductor)",
        r"still\s+(?:energis|energiz|pressuris|pressuriz)\w*",
        r"break(?:ing)?\s+containment",
    ],
    "hot_work": [
        r"hot\s+work",
        r"weld(?:ing|er)",
        r"(?:gas|flame)\s+cutting",
        r"grinding\s+(?:near|in|adjacent)",
        r"fire\s+watch",
        r"ignition\s+source",
        r"spark\w*\s+(?:near|in|fell|landed)",
    ],
    "line_of_fire": [
        r"line\s+of\s+fire",
        r"struck\s+by",
        r"caught\s+(?:in|between)",
        r"pinch\s+point",
        r"crush(?:ed|ing)",
        r"rotating\s+(?:equipment|machinery)",
        r"stood?\s+(?:under|beneath)",
        r"whip(?:ping|lash)",
    ],
    "safe_mechanical_lifting": [
        r"suspended\s+load",
        r"under\s+(?:the\s+)?(?:suspended\s+)?load",
        r"crane\s+(?:lift|operation|failure)",
        r"sling\s+(?:failed|broke|snapped)",
        r"rigging",
        r"lift(?:ing)?\s+plan",
        r"dropped\s+(?:object|load)",
    ],
    "work_authorisation": [
        r"(?:no|without|invalid|expired|missing)\s+(?:valid\s+)?permit",
        r"permit\s+(?:was\s+)?(?:not|never|expired|invalid|missing)",
        r"work(?:ing)?\s+without\s+(?:a\s+)?(?:permit|authoris|authoriz)\w*",
        r"unauthoris(?:ed)?\s+work",
        r"unauthoriz(?:ed)?\s+work",
        r"job\s+safety\s+analysis\s+(?:was\s+)?not",
    ],
    "working_at_height": [
        r"working\s+at\s+heights?",
        r"fell\s+(?:from|off|through)",
        r"fall\s+(?:from|to\s+lower)",
        r"scaffold\w*",
        r"(?:safety\s+)?harness",
        r"ladder",
        r"unprotected\s+edge",
        r"open\s+(?:hole|hatch|grating)",
        r"derrick",
    ],
}

_DIRECT_RES: dict[str, re.Pattern] = {
    rule: re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE)
    for rule, pats in DIRECT_RULE_PATTERNS.items()
}

W_FAILED_BARRIER = 0.55
W_DIRECT_PHRASE = 0.45
W_STATED_HAZARD = 0.40
W_ACTIVITY = 0.30
W_IMPLIED_HAZARD = 0.15


@dataclass
class RuleMapping:
    rule: str | None
    rule_name: str
    score: float
    rationale: list[str] = field(default_factory=list)
    all_scores: dict[str, float] = field(default_factory=dict)

    @property
    def secondary_rules(self) -> list[str]:
        """Other rules with meaningful evidence, strongest first."""
        others = [
            (r, s) for r, s in self.all_scores.items() if r != self.rule and s >= 0.30
        ]
        others.sort(key=lambda x: -x[1])
        return [kb.IOGP_RULES[r]["name"] for r, _ in others[:2]]

    def explain(self) -> str:
        """One paragraph an HSE professional can read and challenge."""
        if not self.rule:
            return (
                "No Life-Saving Rule could be mapped from this narrative. The report "
                "does not contain enough detail about the activity, energy source or "
                "controls involved. Manual HSE classification is required."
            )
        reasons = "; ".join(self.rationale)
        return (
            f"Mapped to {self.rule_name} because {reasons}. "
            f"{kb.IOGP_RULES[self.rule]['statement']}"
        )


def map_rule(narrative: str, extraction: ExtractionResult) -> RuleMapping:
    """Score all nine rules and return the best-supported mapping."""
    text = normalise_text(narrative)
    scores: dict[str, float] = {k: 0.0 for k in kb.IOGP_RULES}
    reasons: dict[str, list[str]] = {k: [] for k in kb.IOGP_RULES}

    # 1. Failed barriers - the strongest signal available.
    for b in extraction.failed_barriers:
        scores[b.rule] += W_FAILED_BARRIER * b.weight
        reasons[b.rule].append(f'the control "{b.label}" failed or was absent')

    # 2. Direct rule language in the narrative.
    for rule, rx in _DIRECT_RES.items():
        m = rx.search(text)
        if m:
            scores[rule] += W_DIRECT_PHRASE
            reasons[rule].append(f'the narrative states "{m.group(0).strip()}"')

    # 3. Hazards named by the reporter.
    for h in extraction.hazards:
        spec = kb.HAZARDS[h]
        scores[spec["rule"]] += W_STATED_HAZARD * spec["sif_weight"]
        reasons[spec["rule"]].append(f"the hazard {spec['label']} is present")

    # 4. Activity being performed.
    for act in extraction.activities:
        rule = ACTIVITY_RULE.get(act)
        if rule:
            scores[rule] += W_ACTIVITY
            reasons[rule].append(f"the activity is {kb.ACTIVITIES[act]['label']}")

    # 5. Hazards merely implied - weakest channel.
    for h in extraction.implied_hazards:
        spec = kb.HAZARDS[h]
        scores[spec["rule"]] += W_IMPLIED_HAZARD * spec["sif_weight"]

    best_rule = max(scores, key=lambda k: scores[k])
    best_score = scores[best_rule]

    if best_score < 0.25:
        return RuleMapping(
            rule=None, rule_name="Unmapped", score=best_score, all_scores=scores
        )

    # De-duplicate rationale while preserving order.
    seen: set[str] = set()
    rationale = [r for r in reasons[best_rule] if not (r in seen or seen.add(r))]

    return RuleMapping(
        rule=best_rule,
        rule_name=kb.IOGP_RULES[best_rule]["name"],
        score=round(best_score, 4),
        rationale=rationale,
        all_scores={k: round(v, 4) for k, v in scores.items()},
    )
