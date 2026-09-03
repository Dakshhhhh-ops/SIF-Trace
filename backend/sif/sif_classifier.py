"""
SIF-potential classification.

Architecture
------------
Two independent estimators, deliberately kept separate and then combined:

  1. TF-IDF + Logistic Regression over the narrative       (learned)
  2. Energy/barrier rule score from the extraction engine  (knowledge-driven)

Keeping them apart matters. The learned model generalises to phrasing the rules
never anticipated; the rule score stays explainable and works on day one with no
training data. Blending gives a system that degrades gracefully instead of
failing silently.

Outcome masking - the most important design decision in this module
-------------------------------------------------------------------
The ground-truth label is derived from OSHA's coded injury fields, and the
narratives frequently state the injury outright:

    "...his left ring finger got caught in between and was amputated."

A model trained on raw text would learn `amputated -> SIF` and score ~0.95 AUC
while having learned nothing of value. It would be reading the CONSEQUENCE.

But this system has to run on Unsafe Act, Unsafe Condition and Near-Miss
reports, where by definition NOBODY HAS BEEN HURT YET and no outcome word
exists. A model that depends on outcome vocabulary is useless on exactly the
reports the problem statement cares about.

So outcome language is masked out of the training text. The model is forced to
learn from the CIRCUMSTANCES - the activity, the equipment, the energy source
and the state of the controls. Metrics drop, and that drop is the honest cost of
building something that works on a near-miss report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from . import knowledge as kb
from .precursor_extractor import ExtractionResult, extract
from .preprocessing import normalise_text

# --------------------------------------------------------------------------
# Outcome masking
# --------------------------------------------------------------------------

# Injury-outcome vocabulary. Replaced with a neutral placeholder so the model
# cannot key on the consequence instead of the precursor.
OUTCOME_PATTERNS: list[str] = [
    r"\bamputat\w*",
    r"\bavulsion\w*",
    r"\bdeglov\w*",
    r"\bsever(?:ed|ing)\b",
    r"\bfractur\w*",
    r"\bbroke[n]?\s+(?:his|her|their|the)?\s*(?:leg|arm|hand|finger|wrist|ankle|hip|rib|back|neck|skull|pelvis|femur|jaw)\w*",
    r"\blacerat\w*",
    r"\bcontusion\w*",
    r"\babrasion\w*",
    r"\bcrush(?:ed|ing)?\s+(?:injur\w*|his|her|their)",
    r"\bhospitali[sz]\w*",
    r"\badmitted\s+to\s+(?:the\s+)?hospital\w*",
    r"\bemergency\s+room\b",
    r"\btransported\s+to\s+(?:a|the)\s+(?:hospital|clinic|medical)\w*",
    r"\bair-?lifted\b",
    r"\bfatal\w*",
    r"\bdied\b",
    r"\bdeath\b",
    r"\bdeceased\b",
    r"\bkilled\b",
    r"\bpronounced\s+dead\b",
    r"\bunconscious\w*",
    r"\bconcussion\w*",
    r"\bintracranial\w*",
    r"\bparaly[sz]\w*",
    r"\bspinal\s+(?:cord\s+)?injur\w*",
    r"\bburn(?:s|ed)?\s+(?:to|on|over)\s+\w+",
    r"\b(?:first|second|third)[- ]degree\s+burn\w*",
    r"\binternal\s+(?:injur|bleed)\w*",
    r"\bpunctur\w*\s+(?:lung|organ)\w*",
    r"\bsustained\s+(?:an?\s+)?injur\w*",
    r"\bsuffered\s+(?:an?\s+)?\w+",
    r"\binjur(?:y|ies|ed)\b",
    r"\bwound\w*",
    r"\bstitches\b",
    r"\bsurgery\b",
    r"\bamputee\b",
    r"\btreated\s+for\b",
]

_OUTCOME_RE = re.compile("|".join(f"(?:{p})" for p in OUTCOME_PATTERNS), re.IGNORECASE)

MASK_TOKEN = " outcomemasked "


def mask_outcome(text: str) -> str:
    """Replace injury-outcome language with a neutral token."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", _OUTCOME_RE.sub(MASK_TOKEN, text)).strip()


# --------------------------------------------------------------------------
# Knowledge-driven score
# --------------------------------------------------------------------------


def rule_score(extraction: ExtractionResult) -> float:
    """
    Energy-barrier SIF score in [0, 1], computed without any training data.

    Mirrors how an HSE professional reads a report:
        Is a lethal-capable energy source involved?   -> hazard energy
        Did a critical control fail?                  -> barrier failure
        Did the outcome confirm the energy released?  -> severity corroboration

    Hazard energy dominates, because a failed permit around a low-energy task is
    a compliance issue, whereas a failed gas test on a vessel entry can kill.
    """
    hazard = extraction.max_hazard_weight

    failed = extraction.failed_barriers
    if failed:
        strongest = max(b.weight for b in failed)
        # Multiple independent failed controls compound the exposure.
        breadth = min(1.0, 0.75 + 0.25 * (len(failed) - 1))
        barrier = strongest * breadth
    else:
        barrier = 0.0

    severity = extraction.severity_score

    score = 0.50 * hazard + 0.35 * barrier + 0.15 * severity

    # A high-energy hazard with NO control failure is still meaningful exposure,
    # but should not reach the SIF threshold on hazard presence alone.
    if hazard > 0 and not failed:
        score = min(score, 0.48)

    return float(min(1.0, max(0.0, score)))


# --------------------------------------------------------------------------
# Classifier
# --------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    is_sif: bool
    confidence: float
    model_probability: float
    rule_probability: float
    label: str = ""
    top_terms: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.label = "SIF-Potential" if self.is_sif else "Non-SIF-Potential"


class SIFClassifier:
    """
    Hybrid SIF-potential classifier.

    Works untrained (rule score only) and improves when `fit` is called, so the
    application never depends on a model file existing.
    """

    def __init__(
        self,
        blend_model: float = 0.65,
        threshold: float = 0.50,
        mask_outcomes: bool = True,
    ) -> None:
        self.blend_model = blend_model
        self.threshold = threshold
        self.mask_outcomes = mask_outcomes
        self.pipeline: Pipeline | None = None
        self.is_fitted = False
        self._feature_names: np.ndarray | None = None
        self._coefs: np.ndarray | None = None

    # -- text preparation -------------------------------------------------
    def _prepare(self, texts) -> list[str]:
        out = []
        for t in texts:
            t = normalise_text(t)
            if self.mask_outcomes:
                t = mask_outcome(t)
            out.append(t)
        return out

    # -- training ---------------------------------------------------------
    def fit(self, narratives, labels) -> "SIFClassifier":
        X = self._prepare(narratives)
        y = np.asarray(labels)

        base = LogisticRegression(
            max_iter=2000,
            C=4.0,
            class_weight="balanced",
            solver="liblinear",
        )
        self.pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=3,
                        max_df=0.85,
                        sublinear_tf=True,
                        strip_accents="unicode",
                        stop_words="english",
                    ),
                ),
                ("clf", base),
            ]
        )
        self.pipeline.fit(X, y)
        self.is_fitted = True

        vec = self.pipeline.named_steps["tfidf"]
        clf = self.pipeline.named_steps["clf"]
        self._feature_names = vec.get_feature_names_out()
        self._coefs = clf.coef_[0]
        return self

    # -- inference --------------------------------------------------------
    def _model_proba(self, narratives) -> np.ndarray:
        if not self.is_fitted or self.pipeline is None:
            return np.full(len(narratives), np.nan)
        return self.pipeline.predict_proba(self._prepare(narratives))[:, 1]

    def predict_one(
        self, narrative: str, extraction: ExtractionResult | None = None
    ) -> ClassificationResult:
        ex = extraction if extraction is not None else extract(narrative)
        rule_p = rule_score(ex)

        if self.is_fitted:
            model_p = float(self._model_proba([narrative])[0])
            blended = self.blend_model * model_p + (1 - self.blend_model) * rule_p
        else:
            model_p = float("nan")
            blended = rule_p

        return ClassificationResult(
            is_sif=blended >= self.threshold,
            confidence=round(float(blended), 4),
            model_probability=round(model_p, 4) if model_p == model_p else float("nan"),
            rule_probability=round(rule_p, 4),
            top_terms=self.explain_terms(narrative) if self.is_fitted else [],
        )

    def predict_batch(self, narratives, extractions=None) -> list[ClassificationResult]:
        narratives = list(narratives)
        if extractions is None:
            extractions = [extract(n) for n in narratives]
        rule_ps = np.array([rule_score(e) for e in extractions])

        if self.is_fitted:
            model_ps = self._model_proba(narratives)
            blended = self.blend_model * model_ps + (1 - self.blend_model) * rule_ps
        else:
            model_ps = np.full(len(narratives), np.nan)
            blended = rule_ps

        return [
            ClassificationResult(
                is_sif=bool(b >= self.threshold),
                confidence=round(float(b), 4),
                model_probability=round(float(m), 4) if m == m else float("nan"),
                rule_probability=round(float(r), 4),
            )
            for b, m, r in zip(blended, model_ps, rule_ps)
        ]

    # -- explainability ---------------------------------------------------
    def explain_terms(self, narrative: str, top_n: int = 6) -> list[tuple[str, float]]:
        """Terms in THIS narrative that pushed the model toward SIF-potential."""
        if not self.is_fitted or self.pipeline is None:
            return []
        vec = self.pipeline.named_steps["tfidf"]
        x = vec.transform(self._prepare([narrative]))
        _, cols = x.nonzero()
        scored = [
            (self._feature_names[c], float(x[0, c] * self._coefs[c])) for c in cols
        ]
        scored.sort(key=lambda t: -t[1])
        return [(t, round(w, 4)) for t, w in scored[:top_n] if w > 0]

    def global_top_terms(self, top_n: int = 25) -> dict[str, list[tuple[str, float]]]:
        """Strongest learned indicators either way - a sanity check for HSE review."""
        if not self.is_fitted or self._coefs is None:
            return {"sif": [], "non_sif": []}
        order = np.argsort(self._coefs)
        return {
            "sif": [
                (str(self._feature_names[i]), round(float(self._coefs[i]), 4))
                for i in order[::-1][:top_n]
            ],
            "non_sif": [
                (str(self._feature_names[i]), round(float(self._coefs[i]), 4))
                for i in order[:top_n]
            ],
        }
