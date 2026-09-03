"""
Text normalisation for free-text safety reports.

Safety reports are written by field personnel under time pressure. They contain
abbreviations, inconsistent spacing, ALL-CAPS shouting, British/American spelling
mixes and domain shorthand. Normalising these before matching materially improves
recall without needing a larger model.
"""

from __future__ import annotations

import re
import unicodedata

# Domain shorthand -> expanded form. Applied on word boundaries, case-insensitive.
# Expansion (rather than contraction) keeps the knowledge-base patterns readable.
ABBREVIATIONS: dict[str, str] = {
    "ptw": "permit to work",
    "loto": "lock out tag out",
    "jsa": "job safety analysis",
    "jha": "job hazard analysis",
    "ppe": "personal protective equipment",
    "scba": "self contained breathing apparatus",
    "h2s": "hydrogen sulphide",
    "lel": "lower explosive limit",
    "esd": "emergency shutdown",
    "psv": "pressure safety valve",
    "bop": "blow out preventer",
    "swl": "safe working load",
    "mewp": "mobile elevating work platform",
    "ndt": "non destructive testing",
    "mcc": "motor control centre",
    "ivms": "in vehicle monitoring system",
    "frc": "flame retardant coverall",
    "ua": "unsafe act",
    "uc": "unsafe condition",
    "nm": "near miss",
    "hse": "health safety environment",
    "sop": "standard operating procedure",
    "toolbox": "tool box",
    "workover": "work over",
    "firewatch": "fire watch",
    "lockout": "lock out",
    "tagout": "tag out",
    "wellhead": "well head",
    "flowline": "flow line",
    "hv": "high voltage",
    "rtc": "road traffic collision",
}

# Common misspellings seen in field reports.
SPELLING_FIXES: dict[str, str] = {
    "isolaton": "isolation",
    "isoltion": "isolation",
    "premit": "permit",
    "permitt": "permit",
    "barricading": "barricading",
    "barricated": "barricaded",
    "harnes": "harness",
    "scafolding": "scaffolding",
    "scaffholding": "scaffolding",
    "confind": "confined",
    "welding": "welding",
    "conected": "connected",
    "recieved": "received",
    "occured": "occurred",
    "manhole": "man hole",
}

_WS_RE = re.compile(r"\s+")
_PUNCT_SPACE_RE = re.compile(r"\s*([,;:])\s*")
_MULTI_DOT_RE = re.compile(r"\.{2,}")


def normalise_text(text: str) -> str:
    """
    Canonical form used for all pattern matching.

    Lower-cases, strips accents/control characters, expands domain abbreviations
    and repairs frequent misspellings. The ORIGINAL narrative is always preserved
    separately - this output is for matching only, never for display.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Unicode normalise and drop control chars (field reports often carry \x00, \x1a)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))

    text = text.lower()

    # Normalise separators that break word boundaries
    text = text.replace("/", " / ").replace("\\", " ")
    text = _MULTI_DOT_RE.sub(". ", text)
    text = _PUNCT_SPACE_RE.sub(r"\1 ", text)

    # Expand abbreviations on word boundaries
    for abbr, full in ABBREVIATIONS.items():
        text = re.sub(rf"\b{re.escape(abbr)}\b", full, text)

    # Repair misspellings
    for wrong, right in SPELLING_FIXES.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)

    return _WS_RE.sub(" ", text).strip()


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[a-z0-9])|(?<=[.!?])\s+(?=[A-Z])|\n+")

# Clause connectors. Splitting on these matters because a single sentence often
# contains one control that held and one that failed:
#   "the permit was valid but gas testing had not been done"
_CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:;|,\s+(?:but|however|although|though|whereas|while|and\s+then)\b|\b(?:but|however|although|though|whereas)\b)\s*"
)


def split_sentences(text: str) -> list[str]:
    """Split normalised text into sentences."""
    if not text:
        return []
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text) if p and p.strip()]
    return parts or [text.strip()]


def split_clauses(text: str) -> list[str]:
    """
    Split into clauses for barrier-status resolution.

    Contrastive connectors ("but", "however") are genuine polarity boundaries in
    safety narratives, so a control mentioned after one must not inherit the
    status of a control mentioned before it.
    """
    clauses: list[str] = []
    for sentence in split_sentences(text):
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            clause = clause.strip(" ,.;:")
            if clause:
                clauses.append(clause)
    return clauses or ([text.strip()] if text.strip() else [])


def clean_for_display(text: str) -> str:
    """Light cleanup for showing the original narrative in the UI."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or not unicodedata.category(ch).startswith("C"))
    return _WS_RE.sub(" ", text).strip()
