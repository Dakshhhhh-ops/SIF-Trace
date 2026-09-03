"""
Central configuration for SIF-Trace.

Every threshold that changes what the dashboard shows lives here and is exposed
through the Settings page, so an HSE team can retune the system without a code
change. Defaults are conservative: the cost of a missed SIF precursor is far
higher than the cost of an extra report in the review queue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# --------------------------------------------------------------------------
# OIL operational context
#
# These are OIL's publicly known operating areas in Upper Assam, Rajasthan,
# and the KG Basin. They are used to give demo records a realistic operational
# geography. See DATA_PROVENANCE in build_corpus.py: when narratives come from a
# public dataset, the SITE ATTRIBUTION IS SYNTHETIC and is labelled as such
# everywhere it is displayed.
# --------------------------------------------------------------------------

OIL_FIELDS: list[str] = [
    "Duliajan",
    "Naharkatiya",
    "Moran",
    "Jorajan",
    "Hapjan",
    "Shalmari",
    "Barekuri",
    "Baghjan",
    "Dikom",
    "Kusijan",
    "Makum",
    "Tengakhat",
    "Chabua",
    "Digboi",
    "Kumchai",
    "Jaisalmer - Tanot",
    "Jaisalmer - Dandewala",
    "KG Basin - Kakinada",
]

ASSET_TYPES: list[str] = [
    "Drilling Rig",
    "Workover Rig",
    "Oil Collecting Station",
    "Group Gathering Station",
    "Crude Oil Pump Station",
    "Gas Compressor Station",
    "LPG Plant",
    "Pipeline Section",
    "Central Workshop",
    "Well Head",
]


# --------------------------------------------------------------------------
# Scoring and threshold configuration
# --------------------------------------------------------------------------


@dataclass
class Thresholds:
    """Tunable decision boundaries, surfaced on the Settings page."""

    # A report is flagged SIF-Potential at or above this model probability.
    sif_confidence: float = 0.50

    # Reports the model is unsure about are queued for human review. Anything
    # between these bounds is treated as "the model should not decide alone".
    review_low: float = 0.35
    review_high: float = 0.65

    # Risk banding on the combined risk score (0-1).
    risk_critical: float = 0.75
    risk_high: float = 0.55
    risk_medium: float = 0.35

    # Site/activity ranking bands on SIF density (0-1).
    density_critical: float = 0.45
    density_high: float = 0.30
    density_medium: float = 0.15

    # A site needs at least this many reports before its density is ranked, so a
    # location with 1 report and 1 SIF does not top the table at 100%.
    min_reports_for_ranking: int = 5

    # A precursor combination must recur at least this often to be a "pattern".
    min_pattern_occurrences: int = 3

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskWeights:
    """
    Weights for the composite risk score.

    Risk is deliberately NOT the model probability alone. A report can be
    confidently SIF-potential yet involve a lower-energy hazard, and a report
    with a failed critical barrier around a high-energy source deserves
    attention even when the text is ambiguous.
    """

    model_confidence: float = 0.40
    hazard_energy: float = 0.30
    barrier_failure: float = 0.20
    outcome_severity: float = 0.10

    def normalised(self) -> dict[str, float]:
        total = (
            self.model_confidence
            + self.hazard_energy
            + self.barrier_failure
            + self.outcome_severity
        )
        return {
            "model_confidence": self.model_confidence / total,
            "hazard_energy": self.hazard_energy / total,
            "barrier_failure": self.barrier_failure / total,
            "outcome_severity": self.outcome_severity / total,
        }


@dataclass
class Settings:
    thresholds: Thresholds = field(default_factory=Thresholds)
    risk_weights: RiskWeights = field(default_factory=RiskWeights)

    # Demo-mode banner state. Flipped to False only when a dataset the operator
    # asserts is real OIL data is loaded.
    demo_mode: bool = True
    dataset_name: str = "No dataset loaded"

    def as_dict(self) -> dict:
        return {
            "thresholds": self.thresholds.as_dict(),
            "risk_weights": asdict(self.risk_weights),
            "demo_mode": self.demo_mode,
            "dataset_name": self.dataset_name,
        }


SETTINGS = Settings()

# Mandatory disclaimer text. Referenced by the API and rendered by the UI.
DEMO_BANNER = "DEMO DATA - NOT ACTUAL OIL RECORDS"
DECISION_SUPPORT_NOTICE = (
    "AI output is a decision-support signal and requires qualified HSE verification."
)
TAGLINE = "AI prioritises. HSE decides."
