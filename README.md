# SIF-Trace

**AI/NLP Engine to Detect Serious Injury & Fatality (SIF) Precursors**

Smart India Hackathon 2026 · Problem Statement **SIH26165** · Oil India Limited

> **AI prioritises. HSE decides.**
> This is decision support. It does not replace qualified HSE professionals.

---

## 1. The safety problem this exists to solve

Oil India Limited collects large volumes of **Unsafe Act (UA)**, **Unsafe
Condition (UC)**, **near-miss** and **incident** reports through its HSSE
platform. Today these are triaged manually, monthly or quarterly.

The difficulty is not volume. It is that **a report can describe a trivial
outcome while containing a condition that could have killed somebody.** A
technician who enters a vessel before the gas test is complete and walks out
unharmed generates the same paperwork as someone who trips on a hose.

Global research established that these are not the same population of events:

| United States, over 15 years | Change |
| --- | --- |
| Non-fatal accidents | **−51%** |
| Fatalities | **−25.5%** |

Driving down minor injuries did **not** drive down deaths at the same rate,
because low-severity incidents and fatalities do not share the same causes
(DEKRA, Martin & Black 2015; EEI SIF Precursor Model; VelocityEHS PSIF
classifier, 2024). Leading operators therefore separately flag the **~20–25% of
reports that carry genuine fatal potential** and direct interventions there.

**SIF-Trace produces that flag automatically**, and aggregates it into the
question an HSE manager actually needs answered: *where should I intervene
first?*

---

## 2. What the system does

For every free-text report:

1. **Classifies** it as SIF-Potential or Non-SIF-Potential, with a confidence
2. **Maps** it to the relevant **IOGP Life-Saving Rule** (Report 459), with a
   written explanation
3. **Extracts** the activity, hazard, exposure, precursor and **failed barrier**
4. **Scores** composite risk and routes uncertain or critical reports to a human
   review queue

Across the whole dataset it then:

5. **Mines recurring precursor patterns** — combinations that repeat across sites
6. **Ranks sites and activities by SIF-precursor density**, not raw count

### What it explicitly does *not* claim

It does **not** predict fatalities, predict accidents, or prevent deaths
automatically. It detects **precursor signals** and prioritises reports for
qualified human review.

---

## 3. Quick start

**Prerequisites:** Python 3.11+, Node 18+

```bash
# 1. Backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cd backend
../.venv/Scripts/python -m uvicorn main:app --port 8000
```

```bash
# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The demo corpus loads automatically — the
dashboard is never empty.

API docs are at **http://localhost:8000/docs**.

---

## 4. Architecture

```
                 CSV  (upload, or the bundled demo corpus)
                  │
                  ▼
        data_loader.py      column mapping by name, then by content
                  │
                  ▼
        preprocessing.py    normalise, expand abbreviations, split clauses
                  │
                  ▼
   precursor_extractor.py   activity · hazard · exposure
                  │         BARRIER STATUS: held / failed / unknown
                  ▼
      sif_classifier.py     TF-IDF + Logistic Regression  ⊕  energy/barrier rules
                  │
                  ▼
        iogp_mapper.py      → one of nine Life-Saving Rules, with rationale
                  │
                  ▼
        risk_engine.py      composite risk · density ranking · review routing
                  │
                  ▼
     pattern_detector.py    recurring precursor combinations
                  │
                  ▼
          pipeline.py       in-memory analysed dataset (analyse once, serve many)
                  │
                  ▼
            main.py         FastAPI REST
                  │
                  ▼
       React dashboard      6 pages
```

```
SIF-Trace/
├── backend/
│   ├── sif/
│   │   ├── knowledge.py            ← all domain knowledge lives here
│   │   ├── preprocessing.py
│   │   ├── precursor_extractor.py  ← context-aware barrier resolution
│   │   ├── sif_classifier.py       ← hybrid model + outcome masking
│   │   ├── iogp_mapper.py          ← Life-Saving Rule mapping (tunable)
│   │   ├── pattern_detector.py
│   │   ├── risk_engine.py
│   │   ├── data_loader.py
│   │   ├── pipeline.py
│   │   └── config.py               ← every threshold
│   └── main.py                     ← FastAPI
├── data/
│   ├── build_corpus.py             ← corpus builder + provenance rules
│   └── sif_reports.csv             ← 12,864 analysed reports
├── notebooks/
│   ├── build_notebook.py
│   └── sif_training.ipynb          ← full ML walkthrough, executed
└── frontend/src/{pages,components}
```

---

## 5. The AI/NLP approach

### 5.1 Why not just keywords

These two sentences share almost all their vocabulary:

| Narrative | Correct reading |
| --- | --- |
| "confined space permit was valid and gas testing was completed" | controls **held** |
| "worker entered confined space without gas testing or permit" | controls **failed** |

A keyword matcher flags both. It would raise false alarms on well-executed work
and lose HSE trust within a week.

So every barrier mention is resolved to a **status** using four signals, in
priority order:

| Signal | Example | Result |
| --- | --- | --- |
| Ordering | "entered **before** gas testing was completed" | FAILED |
| Negated presence | "permit was **not** valid" | FAILED |
| Failure cue | "**without** gas testing" | FAILED |
| Presence cue | "gas testing **was completed**" | PRESENT |

Scoring is proximity-weighted inside each clause, and clauses split on
contrastive connectors — so *"the permit was valid **but** the fire watch was
missing"* correctly resolves **two opposite statuses in one sentence**.

### 5.2 Outcome masking — the key design decision

The training narratives describe events that already happened, and often state
the injury outright:

> "...his left ring finger got caught in between and **was amputated**."

A model trained on raw text learns `amputated → SIF` and posts a flattering AUC
while having learned nothing useful. It is reading the **consequence**.

But this system must run on **UA, UC and near-miss** reports, where *nobody has
been hurt yet* and no outcome word exists. A model that depends on outcome
vocabulary is useless on exactly the reports that matter most.

So injury-outcome language is masked before vectorising. Measured effect:

| | ROC AUC | Top learned SIF indicators |
| --- | --- | --- |
| Outcome words visible | 0.9222 | `amputation`, `amputated`, rig, pump… |
| **Outcome words masked** | **0.9192** | **`rig`, `steam`, `pump`, `feet`, `truck`, `pipe`, `pressure`, `forklift`** |

Masking costs **0.003 AUC** — so the signal was genuinely in the circumstances
all along. And the learned vocabulary shifts from consequences to **energy
sources and work context**, which is what transfers to a near-miss report.

### 5.3 Hybrid classification

Two independent estimators, deliberately kept separate:

- **Learned:** TF-IDF (1–2 gram) + Logistic Regression, `class_weight="balanced"`
- **Knowledge-driven:** energy/barrier rule score, needing no training data

The learned model generalises to phrasing the rules never anticipated; the rule
score stays explainable and works on day one. Blending means the system degrades
gracefully instead of failing silently, and it runs **before any training data
exists**. The module is structured so a transformer can be dropped in behind the
same interface.

---

## 6. SIF classification and the labelling strategy

The obvious approach — write keyword rules, label the data with them, train a
model on those labels — is **worthless**: the model just re-learns the rules, and
every metric measures how well a model imitates a regex.

So the label comes from a **completely independent source**: OSHA's OIICS
`EventTitle` / `NatureTitle` coding, assigned by OSHA analysts from the event
mechanism, never from our text processing.

The rule applies the **energy-based SIF model** — an event is SIF-potential when
a high-energy source could plausibly have caused death or permanent impairment,
*regardless of the injury that actually resulted*:

| Coded mechanism | Label |
| --- | --- |
| Fall to lower level · caught in running equipment · ignition of vapours · struck by falling object · electrical contact · asphyxiation · vehicle incident · cave-in | **SIF-Potential** |
| Fall on same level · overexertion · environmental heat · repetitive motion · hand-tool injury | **Non-SIF** |

The separation is physical, not lexical: *fall to lower level* and *fall on same
level* are both falls that put people in hospital, but only one has the energy to
kill.

---

## 7. IOGP Life-Saving Rule mapping

All nine rules from IOGP Report 459. Evidence accumulates per rule from four
channels:

| Channel | Weight |
| --- | --- |
| Failed barrier (the control that broke points at the rule it protects) | 0.55 |
| Direct rule language in the narrative | 0.45 |
| Stated hazard | 0.40 |
| Activity being performed | 0.30 |
| Implied hazard (inferred, so weighted lowest) | 0.15 |

Every contribution is recorded, so the UI explains *why* — for example:

> Mapped to **Hot Work** because the control "Fire Watch" failed or was absent;
> the narrative states "hot work"; the activity is Hot Work / Welding. Control
> flammables and ignition sources.

A report with no evidence returns **Unmapped** rather than a guess. Mapping logic
lives in `iogp_mapper.py`, separate from the model, so HSE teams can refine it
without retraining anything.

---

## 8. Precursor extraction

For each report the engine extracts activity, hazard, exposure, precursor and
failed barrier. Worked example:

**Input:** *"Technician entered a confined space before gas testing was completed."*

| Field | Output |
| --- | --- |
| Activity | Confined Space Entry |
| Hazard | Toxic / Oxygen-Deficient Atmosphere *(implied by activity)* |
| Exposure | Person inside confined space with restricted egress |
| Precursor | Toxic atmosphere exposure · Gas Testing Not Performed |
| Failed barrier | Gas Testing / Atmospheric Monitoring |
| IOGP Rule | Confined Space |
| Classification | SIF-Potential |

A **precursor requires both** an exposure and a control that did not hold.
Confined-space entry with a valid permit and a completed gas test is *a job done
properly* and yields **zero precursors** — never a false alarm.

---

## 9. Recurring pattern detection

Classifying one report describes one report. Telling an HSE manager that *"Hot
Work — Fire Watch Missing"* has occurred N times across M locations tells them
**where to send an intervention**. Four families are mined:

```
rule + barrier                  Hot Work — Fire Watch Missing
activity + barrier              Welding — Fire Watch Missing
activity + location + barrier   Welding at Moran — Fire Watch Missing
hazard + activity + location    Flammable Release during Welding at Moran
```

**Normalisation is structural, not fuzzy.** `fire watcher absent`, `no fire
watch`, `fire watch not available` and `firewatch missing` all collapse to one
concept automatically, because the extractor resolves a barrier **key + status**
rather than matching surface strings. No string clustering is required.

Patterns are ranked by **breadth first** — a pattern spanning many sites is a
systemic failure, not a local one. A combination must recur at least 3 times
(configurable) to qualify, so a single odd report never becomes a "pattern".

---

## 10. Site and activity risk ranking

Ranking is by **density**, never raw count:

```
SIF Density = SIF-potential reports at site / total reports from site
```

A site filing 400 reports will out-count a site filing 20 without being more
dangerous. In the demo corpus this inversion is visible: the site with the
**second-highest report volume ranks Low**, because its *rate* is below baseline.

Absolute density thresholds cannot work across datasets — 30% is unremarkable in
a corpus averaging 28% and alarming in one averaging 8%. So each group is banded
on its **ratio to the corpus baseline** and must be **statistically significant**
(one-sided z ≥ 1.64, normal approximation to the binomial) before being called
High or Critical.

| Band | Condition |
| --- | --- |
| Critical | ≥ 1.40× baseline **and** significant |
| High | ≥ 1.15× baseline **and** significant |
| Medium | ≥ 1.00× baseline |
| Low | below baseline |

This also prevents a site with 2 reports and 1 SIF being flagged as a
50%-density crisis. Groups below the minimum report count are shown but marked
**Unranked** rather than hidden.

---

## 11. Validation

Metrics come from a **held-out test split the model never saw**. Training-set
scores would flatter the model and mislead the HSE team reading them.

| Metric | Value |
| --- | --- |
| Accuracy | 0.852 |
| Precision | 0.672 |
| Recall | **0.796** |
| F1 | 0.729 |
| ROC AUC | 0.919 |

**Recall is prioritised deliberately.** The two errors are not symmetric: a false
positive costs a reviewer a few minutes; a false negative is a fatal-potential
precursor that returns to the monthly queue and is never acted on.

**If a loaded dataset has no verified labels, the Validation page says
"Validation dataset not yet available" and shows no numbers.** Inventing metrics
would be worse than showing none.

### Human review queue

A report is routed to a human when either:

- confidence falls inside the uncertainty band (default 0.35–0.65), or
- risk is **Critical** — a human must sign it off regardless of confidence

---

## 12. Dataset

### 12.1 Data provenance — read before quoting any number

**Actual OIL HSSE data is confidential and is not used anywhere in this project.**
The demo corpus is built from the **OSHA Severe Injury Reports** public dataset
(105,996 records, Jan 2015 – Nov 2025), filtered to oil & gas NAICS codes.

| Field | Provenance |
| --- | --- |
| `narrative` | **REAL** — verbatim free text written by safety professionals |
| `sif_label` | **REAL** — derived independently from OSHA's OIICS event coding |
| `location`, `asset`, `date` | **SYNTHETIC** — *not* real OIL sites or dates |
| `report_type` | `Incident` on every real record — see below |

**On report types.** Every OSHA record is an injury that already happened, so
labelling one "Unsafe Condition" produced a narrative contradicting its own label
(an unsafe-condition observation ending in surgery). Real records are therefore
all typed **`Incident`**, which is what they are. The UA/UC/Near-Miss layer is
generated separately by `data/synthetic_observations.py` in OIL's operational
register — machine-written, tagged `narrative_provenance=synthetic`, and
**excluded from the model's reported metrics**, which are computed on the real
subset only.

Every row carries these provenance columns, the UI shows
**"DEMO DATA — NOT ACTUAL OIL RECORDS"** on every page, and nothing here is an
OIL operational statistic.

### 12.2 Corpus composition

| | Count |
| --- | --- |
| Total reports | **12,864** |
| SIF-potential | 3,192 (**24.8%** — matches the 20–25% industry benchmark) |
| Real oil & gas records | 3,828 |
| Industrial-analogue negatives | 9,036 |
| Synthetic OIL-style observations | 1,200 |

OSHA SIR is a *severe-injury registry*, so its oil & gas slice is 76%
high-energy. Training on that would produce a model that flags almost everything
— precisely the triage failure this project exists to fix. So **every real oil &
gas record is kept** and the negative class is topped up with low-energy
narratives from construction, manufacturing, utilities and transport, each tagged
`industrial_analogue` so the contribution stays auditable.

Rebuild it yourself:

```bash
python data/build_corpus.py --sir <path-to-SIR.csv> --out data/sif_reports.csv
```

### 12.3 Expected CSV format

**No column name is required to match.** The loader scores columns against known
aliases and, failing that, inspects content — the narrative column is the one
holding long prose. Recognised concepts:

| Canonical | Accepted aliases (examples) |
| --- | --- |
| `report_id` | id, ref_no, observation_id, case_no |
| `date` | reported_date, event_date, incident_date |
| `location` | site, field, area, installation, facility |
| `report_type` | type, category, observation_type |
| `activity` | task, job, work_type, operation |
| `narrative` | description, details, observation, remarks, what_happened |
| `sif_label` | sif, sif_potential, hipo, high_potential |
| `status` | review_status, workflow_status |

Only a narrative column is mandatory. If verified SIF labels are present, the
model retrains on them and real validation metrics appear.

---

## 13. Deployment

For a laptop demo the two-terminal Quick Start above is enough. To put it on a
public URL, build the frontend and let FastAPI serve it - **one process, one
origin, no CORS, no proxy**:

```bash
cd frontend && npm run build      # emits frontend/dist/
cd ../backend
export SIF_ADMIN_TOKEN="choose-a-long-random-value"   # see below
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Everything is then on `http://<host>:8000` - dashboard, deep links and API.

### Write protection

Reads are public; the dashboard is meant to be looked at. But **upload and
threshold changes mutate global state every viewer sees**, so on a public URL
they must not be open to anyone holding the link.

Setting `SIF_ADMIN_TOKEN` requires an `X-SIF-Token` header on
`POST /api/upload`, `POST /api/reload-demo` and `PATCH /api/settings/thresholds`.
Paste the token once under **Settings → Write Access** and the browser keeps it.
Leave the variable unset for a laptop demo and the API stays fully open;
`/api/health` reports `write_protected` either way, so the state is never a
surprise.

### Cold start

First analysis of the corpus takes ~28 s, which exceeds the health-check window
on most free tiers - the service gets killed before it ever answers. The
analysed result is therefore cached to `models/cache/`, cutting cold start to
**~2.6 s**. The cache key covers the CSV's size and mtime *and* a fingerprint of
the engine source, so editing a rule invalidates it rather than silently serving
stale analysis.

### One worker only

`pipeline` is a module-level singleton holding the analysed dataset in memory.
Run **one** worker. With two, an upload lands on a random process and the
dashboard shows different numbers on each refresh. Scaling past one worker needs
shared state (Redis or a database), which is deliberately out of scope here.

| Setting | Value |
| --- | --- |
| Workers | 1 (required) |
| Memory | ~200 MB RSS |
| Cold start | ~2.6 s cached, ~28 s uncached |
| `SIF_ADMIN_TOKEN` | required for a public URL |
| `SIF_ALLOWED_ORIGINS` | only if the frontend is hosted separately |

### Not for operational use

This runs on US OSHA data with proxy labels and no HSE validation. It is a
hackathon prototype. Deploying it against real OIL HSSE reports requires
retraining on OIL data and the validation programme described in section 11.

---

## 14. Example workflow

1. **Start** both servers → the demo corpus auto-loads
2. **Dashboard** → SIF density, ranked sites, IOGP distribution, recurring
   patterns, live alerts
3. **Site ranking** → click the Critical site to filter its reports
4. **Reports** → search `"fire watch"`, filter to SIF-Potential + Critical
5. **Click a report** → original narrative, precursors, failed barriers *with the
   quoted evidence*, IOGP rule *with reasoning*
6. **Precursor Patterns** → find the combination repeating across sites
7. **Validation** → held-out metrics, confusion matrix, human review queue
8. **Settings** → paste your own narrative and watch the pipeline run live;
   retune thresholds and see every view update
9. **Import CSV** → upload your own data; detected column mapping is shown

---

## 15. Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18, Tailwind CSS, Recharts, Lucide, React Router |
| Backend | Python 3.12, FastAPI, Pydantic, Uvicorn |
| ML / NLP | scikit-learn (TF-IDF + Logistic Regression), pandas, NumPy |
| Storage | CSV → in-memory pandas DataFrame |

No Docker, Kubernetes or cloud infrastructure. It runs locally with two commands.

**Performance:** 12,864 reports fully analysed in ~28 s (~2.6 s from cache). Analysis happens once
per upload; every dashboard view is then served from memory. Threshold changes
re-derive views without re-running NLP.

---

## 16. Honest limitations

1. **Domain transfer.** Trained on OSHA severe-injury narratives from US oil &
   gas, not OIL's reports. Indian E&P reporting style, local terminology and
   OIL's own UA/UC taxonomy will differ. **Retraining on OIL data is required
   before operational use.**
2. **Label proxy.** `sif_label` derives from OSHA's coded injury mechanism — a
   defensible, independent proxy for fatal potential, but still a proxy, not an
   HSE professional's SIF determination.
3. **Outcome-bearing training text.** Every training narrative describes an event
   that already happened. Outcome masking mitigates the vocabulary mismatch, but
   genuine UA/UC observations use a different register ("observed that…") that is
   under-represented.
4. **English only.** No Assamese or Hindi, and no code-mixed text.
5. **Synthetic operational context.** Locations, assets, report types and dates
   are constructed. Site rankings demonstrate the **method**; they are not
   findings about any real location.

---

## 17. Future scope

- Fine-tune a domain transformer (SafetyBERT / IndicBERT) once OIL data is
  available; the classifier interface already supports swapping the estimator
- Assamese and Hindi support, including code-mixed narratives
- Active learning: HSE corrections in the review queue feed back as training data
- Temporal trend detection — patterns that are *accelerating*, not just frequent
- Barrier-health scoring per site, tracking which controls degrade over time
- Direct HSSE platform integration for continuous rather than periodic triage

---

## 18. Ethical guardrail

Output is a **decision-support signal requiring qualified HSE verification**.

It must **never** be used for individual performance assessment or disciplinary
action. Doing so would suppress the honest near-miss reporting that the entire
model depends on, and would make the workplace less safe, not more.

> **AI prioritises. HSE decides.**

---

## 19. Attribution

- **IOGP Report 459** — Life-Saving Rules
- **OSHA Severe Injury Reports** — public dataset (US Dept of Labor)
- **DEKRA / Martin & Black (2015)**, **EEI SIF Precursor Model** — energy-based
  SIF methodology

Licensed under the MIT License. See [LICENSE](LICENSE).
