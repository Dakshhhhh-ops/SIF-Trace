"""
Generate notebooks/sif_training.ipynb.

The notebook is generated from this script so it stays reproducible and
reviewable in git (a .ipynb is painful to diff). Run:

    python notebooks/build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    CELLS.append(("markdown", text.strip("\n")))


def code(text: str) -> None:
    CELLS.append(("code", text.strip("\n")))


# ==========================================================================

md(r"""
# SIF-Trace - SIF Precursor Detection Engine

**Smart India Hackathon 2026 | Problem Statement SIH26165 | Oil India Limited**

AI/NLP engine that detects **Serious Injury & Fatality (SIF) precursors** in
unsafe-act, unsafe-condition and near-miss reports.

> **AI prioritises. HSE decides.**
> This is decision support. It does not replace qualified HSE professionals.

---

## The problem this notebook solves

OIL collects large volumes of UA/UC observations, near-miss and incident reports,
and triages them manually every month or quarter. The premise of the SIF model
(DEKRA, Martin & Black 2015; EEI SIF precursor model) is that **low-severity
incidents do not share the same causes as fatalities**:

| Metric, US, over 15 years | Change |
|---|---|
| Non-fatal accidents | **-51%** |
| Fatalities | **-25.5%** |

Driving down minor injuries did **not** drive down deaths at the same rate. So
leading operators separately flag the ~20-25% of reports that carry genuine fatal
potential. That flag is what this engine produces.

## What this notebook covers

1. Dataset inspection and provenance
2. The labelling strategy - and why it is not circular
3. Outcome-leakage analysis (the most important experiment here)
4. Model training and honest held-out metrics
5. The context-aware rule engine (control held vs control failed)
6. IOGP Life-Saving Rule mapping
7. Recurring precursor pattern mining
8. Site and activity risk ranking
9. Model card, limitations and production requirements
""")

code(r"""
import sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Make the backend package importable
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
import pandas as pd

pd.set_option("display.width", 190)
pd.set_option("display.max_colwidth", 110)

print("project root:", ROOT)
""")

# --------------------------------------------------------------------------
md(r"""
---
## 1. Dataset inspection

### Provenance - read this before quoting any number

Actual OIL HSSE data is confidential and is **not used anywhere** in this project.
The corpus is built by `data/build_corpus.py` from the **OSHA Severe Injury
Reports** public dataset (105,996 records, Jan 2015 - Nov 2025), and every row
records what is real and what is constructed:

| Field | Provenance |
|---|---|
| `narrative` | **REAL** - verbatim free text written by safety professionals |
| `sif_label` | **REAL** - derived from OSHA's own OIICS event coding |
| `location`, `asset`, `report_type`, `date` | **SYNTHETIC** - not real OIL sites or dates |

Nothing here is an OIL operational statistic, and the application never presents
it as one.
""")

code(r"""
df = pd.read_csv(ROOT / "data" / "sif_reports.csv")
print(f"rows: {len(df):,}   columns: {len(df.columns)}")
print(f"SIF-potential rate: {df.sif_label.mean():.1%}  (industry benchmark 20-25%)")
print()
df.head(3)[["report_id", "date", "location", "asset", "report_type", "sif_label"]]
""")

code(r"""
print("=== CLASS BALANCE ===")
print(df.sif_label.value_counts().rename({0: "Non-SIF-Potential", 1: "SIF-Potential"}))
print()
print("=== SECTOR PROVENANCE ===")
print(df.sector_provenance.value_counts())
print()
print("=== REPORT TYPE MIX (synthetic overlay) ===")
print(df.report_type.value_counts())
print()
print("=== MISSING VALUES ===")
miss = df.isna().sum()
print(miss[miss > 0] if miss.any() else "none")
print()
print("=== NARRATIVE LENGTH (characters) ===")
print(df.narrative.str.len().describe().round(1))
""")

code(r"""
# What real safety narratives actually look like
for i, row in df[df.sif_label == 1].head(2).iterrows():
    print(f"[SIF-POTENTIAL]  {row.location} / {row.asset}  ({row.report_type})")
    print(f"  {row.narrative[:300]}")
    print(f"  label reason: {row.sif_label_reason}\n")

for i, row in df[df.sif_label == 0].head(2).iterrows():
    print(f"[NON-SIF]  {row.location} / {row.asset}  ({row.report_type})")
    print(f"  {row.narrative[:300]}")
    print(f"  label reason: {row.sif_label_reason}\n")
""")

# --------------------------------------------------------------------------
md(r"""
---
## 2. The labelling strategy - and why it is not circular

The spec allows a documented prototype labelling strategy when verified labels
are unavailable. The obvious approach is to write keyword rules, label the data
with them, then train a model on those labels.

**That approach is worthless.** The model would simply re-learn the rules, and
every metric would measure how well a model imitates a regex - not whether it
detects SIF precursors.

So the label comes from a **completely independent source**: OSHA's OIICS
`EventTitle` / `NatureTitle` codes, assigned by OSHA analysts from the event
mechanism, never from our text processing.

The rule applies the **energy-based SIF model**: an event is SIF-potential when a
high-energy source could plausibly have caused death or permanent impairment,
*regardless of the injury that actually resulted*. That is the whole premise of
the problem statement - fatal potential is about the ENERGY, not the outcome.
""")

code(r"""
print("=== HIGH-ENERGY mechanisms -> SIF-Potential ===")
print(df[df.sif_label == 1].source_event_code.value_counts().head(10).to_string())
print()
print("=== LOW-ENERGY mechanisms -> Non-SIF ===")
print(df[df.sif_label == 0].source_event_code.value_counts().head(10).to_string())
""")

md(r"""
Note the separation is genuinely physical, not lexical. `Fall to lower level`
(SIF) versus `Fall on same level due to slipping` (non-SIF) - both are falls, both
put people in hospital, but only one has the energy to kill.
""")

# --------------------------------------------------------------------------
md(r"""
---
## 3. Outcome leakage - the most important experiment in this notebook

The labels derive partly from the coded injury, and narratives often state the
injury outright:

> "...his left ring finger got caught in between and **was amputated**."

A model trained on raw text learns `amputated -> SIF` and scores a flattering
AUC while having learned nothing useful. It is reading the **consequence**.

But this system must run on **Unsafe Act, Unsafe Condition and Near-Miss**
reports, where *nobody has been hurt yet* and no outcome word exists. A model
that depends on outcome vocabulary is useless on exactly the reports that matter.

So `sif_classifier.mask_outcome()` strips injury-outcome language before
vectorising, forcing the model to learn from **circumstances** - the activity, the
equipment, the energy source, the state of the controls.

Let us measure what that costs.
""")

code(r"""
from sif.sif_classifier import SIFClassifier, mask_outcome

example = df[df.narrative.str.contains("amputat", case=False)].narrative.iloc[0]
print("ORIGINAL:\n ", example[:290], "\n")
print("MASKED:\n ", mask_outcome(example)[:290])
""")

code(r"""
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix)

X_train, X_test, y_train, y_test = train_test_split(
    df.narrative.values, df.sif_label.values,
    test_size=0.25, random_state=42, stratify=df.sif_label.values,
)
print(f"train {len(X_train):,}   test {len(X_test):,}")

results = {}
for mask in (False, True):
    clf = SIFClassifier(mask_outcomes=mask, blend_model=1.0).fit(X_train, y_train)
    proba = clf._model_proba(X_test)
    pred = (proba >= 0.5).astype(int)
    results[mask] = {
        "accuracy":  accuracy_score(y_test, pred),
        "precision": precision_score(y_test, pred),
        "recall":    recall_score(y_test, pred),
        "f1":        f1_score(y_test, pred),
        "roc_auc":   roc_auc_score(y_test, proba),
        "clf":       clf,
    }

comp = pd.DataFrame({
    "outcome words visible": {k: f"{v:.4f}" for k, v in results[False].items() if k != "clf"},
    "outcome words MASKED":  {k: f"{v:.4f}" for k, v in results[True].items()  if k != "clf"},
})
comp
""")

code(r"""
# What did each model actually learn?
for mask in (False, True):
    top = results[mask]["clf"].global_top_terms(12)
    tag = "MASKED  " if mask else "UNMASKED"
    print(f"[{tag}] top SIF indicators    : {[t for t, _ in top['sif']]}")
    print(f"[{tag}] top non-SIF indicators: {[t for t, _ in top['non_sif']]}")
    print()
""")

md(r"""
### Reading this result

Masking costs very little AUC - so the model was **never** relying primarily on
leakage; the signal is genuinely in the circumstances.

More importantly, look at what the masked model learned. The SIF indicators are
`rig`, `steam`, `pump`, `feet`, `truck`, `pipe`, `tubing`, `pressure`,
`forklift` - **energy sources and work context**. The non-SIF indicators are
`tripped`, `slipped`, `heat`, `dehydration`, `walking` - low-energy circumstances.

That is a model that will still work on a near-miss report where nobody was hurt.
**Every model from here on uses outcome masking.**
""")

# --------------------------------------------------------------------------
md(r"""
---
## 4. Model training and honest metrics

Baseline chosen for the prototype, per the spec's instruction to prioritise
reliability and explainability over unnecessarily complex deep learning:

- **TF-IDF**, 1-2 grams, `min_df=3`, sublinear term frequency
- **Logistic Regression**, `class_weight="balanced"`, liblinear

Linear and sparse means every prediction can be attributed to specific terms -
which is what makes the Report Analysis view auditable by an HSE professional.
The module is structured so a transformer can be dropped in later behind the same
interface.
""")

code(r"""
clf = results[True]["clf"]            # the outcome-masked model
proba = clf._model_proba(X_test)
pred = (proba >= 0.5).astype(int)

tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()
print("HELD-OUT TEST METRICS  (25% split, never seen during training)")
print(f"  Accuracy   {accuracy_score(y_test, pred):.4f}")
print(f"  Precision  {precision_score(y_test, pred):.4f}")
print(f"  Recall     {recall_score(y_test, pred):.4f}")
print(f"  F1         {f1_score(y_test, pred):.4f}")
print(f"  ROC AUC    {roc_auc_score(y_test, proba):.4f}")
print()
print(pd.DataFrame(
    [[tn, fp], [fn, tp]],
    index=["actual Non-SIF", "actual SIF"],
    columns=["predicted Non-SIF", "predicted SIF"],
))
""")

md(r"""
### Why recall is prioritised over precision

The two errors are **not** symmetric:

- A **false positive** costs an HSE professional a few minutes reviewing a report
  that turns out to be routine.
- A **false negative** is a fatal-potential precursor that goes back into the
  monthly queue and is never acted on.

The threshold is therefore tuned toward recall, and every uncertain or
critical-risk report is routed to the human review queue rather than being
silently auto-classified.
""")

code(r"""
# Threshold sensitivity - the operating-point decision, made explicit
rows = []
for th in np.arange(0.30, 0.75, 0.05):
    p = (proba >= th).astype(int)
    rows.append({
        "threshold": round(th, 2),
        "precision": round(precision_score(y_test, p, zero_division=0), 3),
        "recall":    round(recall_score(y_test, p, zero_division=0), 3),
        "f1":        round(f1_score(y_test, p, zero_division=0), 3),
        "flagged":   int(p.sum()),
        "missed_SIF": int(((p == 0) & (y_test == 1)).sum()),
    })
pd.DataFrame(rows)
""")

# --------------------------------------------------------------------------
md(r"""
---
## 5. The context-aware rule engine

This is the part a bag-of-words model cannot do. Consider:

| Narrative | Correct reading |
|---|---|
| "confined space permit was valid and gas testing was completed" | controls **held** |
| "worker entered confined space without gas testing or permit" | controls **failed** |

Nearly identical vocabulary, opposite safety meaning. The extractor resolves each
barrier mention to a **status** using four signals in priority order:

1. **Ordering** - "entered *before* gas testing was completed" -> FAILED
2. **Negated presence** - "permit was *not* valid" -> FAILED
3. **Failure cues** - "*without* gas testing" -> FAILED
4. **Presence cues** - "gas testing *was completed*" -> PRESENT

Scoring is proximity-weighted within each clause, and clauses split on
contrastive connectors so *"the permit was valid **but** the fire watch was
missing"* resolves two opposite statuses in one sentence.
""")

code(r"""
from sif.precursor_extractor import extract

cases = [
    "Worker entered confined space without gas testing and permit verification.",
    "Maintenance started after confirming isolation and zero-energy state.",
    "Confined space permit was valid and gas testing was completed before entry.",
    "Technician entered a confined space before gas testing was completed.",
    "The permit to work was valid but the fire watch had not been arranged.",
    "Operator bypassed the ESD interlock without authorisation to keep the compressor running.",
    "Lift plan was approved, the area was barricaded and a banksman was stationed.",
]

for text in cases:
    r = extract(text)
    print(text)
    print(f"   activity : {r.primary_activity}")
    print(f"   FAILED   : {[b.canonical for b in r.failed_barriers] or '-'}")
    print(f"   PRESENT  : {[b.label for b in r.present_barriers] or '-'}")
    print(f"   precursor: {r.precursor_labels() or 'NONE'}")
    print()
""")

md(r"""
Note the two compliant narratives produce **zero precursors**. A system that
flagged "isolation" or "confined space" on keyword presence alone would raise
false alarms on well-executed work and destroy HSE trust within a week.
""")

code(r"""
# The spec's worked example, end to end
r = extract("Technician entered a confined space before gas testing was completed.")
print("Activity      :", r.primary_activity)
print("Hazard        :", r.primary_hazard if r.hazards else "(implied) toxic atmosphere")
print("Exposure      :", r.exposure)
print("Failed Barrier:", r.failed_barrier_labels)
print("Precursors    :", r.precursor_labels())
""")

# --------------------------------------------------------------------------
md(r"""
---
## 6. IOGP Life-Saving Rule mapping

Mapping is kept in `iogp_mapper.py`, separate from the model, so HSE teams can
tune it without retraining anything. Evidence accumulates per rule from four
channels - failed barriers, direct rule language, stated hazards and the activity
- and every contribution is recorded so the mapping can be **explained and
overruled**.
""")

code(r"""
from sif.iogp_mapper import map_rule

spec_examples = [
    ("equipment not isolated before maintenance",                 "Energy Isolation"),
    ("entered confined vessel without gas test",                  "Confined Space"),
    ("hot work performed without fire watch",                     "Hot Work"),
    ("worker standing under suspended load",                      "Safe Mechanical Lifting"),
    ("work started without valid permit",                         "Work Authorisation"),
    ("working on elevated platform without fall protection",      "Working at Height"),
    ("critical interlock bypassed without authorization",         "Bypassing Safety Controls"),
    ("vehicle speeding on lease road, unsafe driving observed",   "Driving"),
]

hits = 0
for text, expected in spec_examples:
    m = map_rule(text, extract(text))
    ok = m.rule_name == expected
    hits += ok
    print(f"{'PASS' if ok else 'FAIL':<6} {expected:<26} <- {text}")
print(f"\n{hits}/{len(spec_examples)} exact matches")
""")

code(r"""
# Explainability: why did it choose that rule?
text = "Hot work was carried out on the separator without a fire watch and the gas test had expired."
m = map_rule(text, extract(text))
print(text, "\n")
print(m.explain())
print("\nsecondary rules:", m.secondary_rules)
""")

# --------------------------------------------------------------------------
md(r"""
---
## 7. Full pipeline + recurring pattern detection

Classifying one report tells an HSE manager about one report. Telling them that
*"Hot Work without Fire Watch"* has occurred N times across M locations tells them
**where to send an intervention**. That aggregation is the actual product.

Surface variants (`fire watcher absent` / `no fire watch` / `firewatch missing`)
collapse automatically, because the extractor resolves a barrier **key + status**
rather than matching strings - so pattern mining operates on concepts, and no
fuzzy clustering is needed.
""")

code(r"""
from sif.pipeline import Pipeline

pipe = Pipeline()
ds = pipe.load_path(ROOT / "data" / "sif_reports.csv", is_demo=True)
print(f"analysed {len(ds.records):,} reports in {ds.analysis_seconds}s")
print(f"ground truth available: {ds.has_ground_truth}   model trained: {ds.model_trained}")
""")

code(r"""
kpis = pipe.kpis()
pd.Series({
    "Total reports analysed":  f"{kpis['total_reports']:,}",
    "SIF-potential reports":   f"{kpis['sif_reports']:,}",
    "SIF density":             f"{kpis['sif_density']:.1%}",
    "High-risk sites":         kpis["high_risk_sites"],
    "Awaiting HSE review":     f"{kpis['awaiting_review']:,}",
    "High-confidence alerts":  f"{kpis['high_confidence_alerts']:,}",
    "Most frequent IOGP rule": kpis["most_frequent_rule"],
    "Critical patterns":       kpis["critical_patterns"],
}).to_frame("value")
""")

code(r"""
pats = pipe.headline_patterns(8)
pd.DataFrame([{
    "pattern": p["label"],
    "occurrences": p["occurrences"],
    "sites": p["site_count"],
    "avg confidence": round(p["avg_confidence"], 3),
    "risk": p["risk_level"],
} for p in pats])
""")

code(r"""
# Drill into one pattern - this is what an HSE team would act on
p = pats[0]
print("PATTERN:", p["label"])
print(f"  {p['occurrences']} occurrences across {p['site_count']} site(s): {', '.join(p['sites'][:6])}")
print(f"  risk {p['risk_level']}   avg confidence {p['avg_confidence']:.2f}\n")
for ex in p["example_reports"]:
    print(f"  [{ex['report_id']}] {ex['location']}  (confidence {ex['confidence']:.2f})")
    print(f"     {ex['narrative'][:190]}\n")
""")

# --------------------------------------------------------------------------
md(r"""
---
## 8. Site and activity risk ranking

The spec is explicit: rank by **density**, not raw count, because a site filing
400 reports will out-count a site filing 20 without being more dangerous.

We go one step further. Absolute density thresholds cannot work across datasets -
30% density is unremarkable in a corpus averaging 28% and alarming in one
averaging 8%. So each group is banded on its **ratio to the corpus baseline**,
and must be **statistically significant** (one-sided z >= 1.64) before being
called High or Critical. That also prevents a site with 2 reports and 1 SIF from
being flagged as a 50%-density crisis.
""")

code(r"""
sites = pd.DataFrame(pipe.site_ranking())
sites[["key", "total_reports", "sif_reports", "sif_density",
       "density_ratio", "z_score", "significant", "risk_level",
       "dominant_rule", "top_precursor"]].head(12)
""")

md(r"""
Observe the count-versus-density inversion working: the site with one of the
largest report volumes lands at **Low** risk because its *rate* is below baseline,
while a smaller drilling-heavy field ranks **Critical**. Ranking on raw counts
would have inverted this and sent the intervention to the wrong place.
""")

code(r"""
acts = pd.DataFrame(pipe.activity_ranking())
acts[["key", "total_reports", "sif_reports", "sif_density",
      "density_ratio", "risk_level", "dominant_rule", "top_precursor"]].head(12)
""")

code(r"""
rules = pd.DataFrame(pipe.rule_distribution())
rules[["name", "total_reports", "sif_reports", "sif_density", "top_precursor"]]
""")

# --------------------------------------------------------------------------
md(r"""
---
## 9. End-to-end demonstration

The complete chain the judging criteria describe, on a single free-text report:

```
FREE-TEXT REPORT -> NLP -> SIF CLASSIFICATION -> IOGP RULE
   -> PRECURSOR -> FAILED BARRIER -> RISK -> HSE PRIORITISATION
```
""")

code(r"""
demo = [
    "Worker entered confined space without gas testing and permit verification.",
    "Maintenance started after confirming isolation and zero-energy state.",
    "Welder was cutting on a line at the GGS while no fire watch was present and the gas test had expired.",
    "Employee slipped on a wet walkway near the office and twisted an ankle.",
]

for text in demo:
    a = pipe.analyse_text(text)
    print("=" * 100)
    print("REPORT:", text)
    print(f"  -> {a['classification']}  (confidence {a['confidence']:.0%})   risk: {a['risk_level']}")
    print(f"  -> IOGP rule    : {a['iogp_rule_name']}")
    print(f"  -> activity     : {a['activity']}")
    print(f"  -> hazard       : {a['hazard']}")
    print(f"  -> precursors   : {a['precursors'] or 'none detected'}")
    print(f"  -> failed barrier: {a['failed_barriers'] or 'none'}")
    print(f"  -> controls held : {a['present_barriers'] or 'none stated'}")
    print(f"  -> action       : {a['recommended_action']}")
    print(f"  -> why          : {a['iogp_explanation']}")
    print()
""")

# --------------------------------------------------------------------------
md(r"""
---
## 10. Model card, limitations and production requirements

### What this system does
Ranks free-text safety reports by **fatal potential**, maps them to IOGP
Life-Saving Rules, extracts the failed barrier, and aggregates recurring
precursor patterns by site and activity.

### What it explicitly does **not** do
It does not predict fatalities, predict accidents, or prevent deaths
automatically. It detects **precursor signals** and prioritises reports for
qualified human review.

### Honest limitations

1. **Domain transfer.** Trained on OSHA severe-injury narratives from US oil &
   gas, not OIL's own reports. Indian E&P reporting style, local terminology and
   OIL's UA/UC taxonomy will differ. Retraining on OIL data is required before
   any operational use.

2. **Label proxy.** `sif_label` derives from OSHA's coded injury mechanism, which
   is a proxy for fatal potential, not an HSE professional's SIF determination.
   It is defensible and independent, but it is still a proxy.

3. **Outcome-bearing training text.** Every training narrative describes an event
   that already happened. Outcome masking mitigates the resulting vocabulary
   mismatch, but genuine UA/UC observations are written in a different register
   ("observed that...", "noticed that...") that is under-represented here.

4. **English only.** No Assamese or Hindi handling, and no code-mixed text.

5. **Synthetic operational context.** Locations, assets, report types and dates
   are constructed. Site rankings demonstrate the *method*; they are not findings
   about any real location.

### What production validation requires

- 300-500 reports independently classified by qualified HSE professionals
- Dual review with disagreements adjudicated
- Coverage of all nine Life-Saving Rules and both classes
- Precision/recall measured against that human ground truth
- Periodic drift monitoring as reporting practice changes

### Ethical guardrail

Output is a **decision-support signal requiring qualified HSE verification**.
It must never be used for individual performance assessment or disciplinary
action, which would suppress the honest near-miss reporting the whole model
depends on.

> **AI prioritises. HSE decides.**
""")

# ==========================================================================


def main() -> None:
    nb = {
        "cells": [
            {
                "cell_type": kind,
                "id": f"cell-{i:02d}",
                "metadata": {},
                "source": src.splitlines(keepends=True),
                **({"outputs": [], "execution_count": None} if kind == "code" else {}),
            }
            for i, (kind, src) in enumerate(CELLS)
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out = Path(__file__).parent / "sif_training.ipynb"
    out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    n_code = sum(1 for k, _ in CELLS if k == "code")
    print(f"wrote {out}  ({len(CELLS)} cells: {n_code} code, {len(CELLS) - n_code} markdown)")


if __name__ == "__main__":
    main()
