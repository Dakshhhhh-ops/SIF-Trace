"""
CSV ingestion with intelligent column mapping.

The spec is explicit: do not assume exact column names. Every HSSE export names
things differently - `narrative`, `description`, `incident_description`,
`observation`, `details`, `remarks`. This module scores each incoming column
against known aliases, and where names give no answer it inspects the CONTENT
(a narrative column is the one holding long prose) so an unlabelled export still
loads.

Malformed input is expected, not exceptional. Every failure produces a message
an operator can act on, never a traceback.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

# Canonical field -> alias fragments, matched against normalised column names.
COLUMN_ALIASES: dict[str, list[str]] = {
    "report_id": ["reportid", "id", "refno", "referenceno", "ticketno", "caseno",
                  "observationid", "incidentid", "srno", "serialno", "no"],
    "date": ["date", "reporteddate", "eventdate", "incidentdate", "occurrencedate",
             "observationdate", "datetime", "reportedon", "createdon"],
    "location": ["location", "site", "field", "area", "installation", "plant",
                 "facility", "block", "station", "region", "workarea", "department"],
    "asset": ["asset", "assettype", "equipment", "unit", "rig", "installationtype"],
    "report_type": ["reporttype", "type", "category", "observationtype", "class",
                    "classification", "reportcategory", "nature"],
    "activity": ["activity", "task", "job", "worktype", "operation", "activitytype",
                 "jobtype", "process"],
    "narrative": ["narrative", "description", "details", "observation", "observed",
                  "remarks", "incidentdescription", "observationdescription",
                  "whathappened", "whatwasobserved", "whatobserved", "eventdescription",
                  "incidentdetails", "finding", "findings", "summary", "text",
                  "comment", "comments", "finalnarrative", "report", "body", "desc"],
    "sif_label": ["siflabel", "sif", "sifpotential", "issif", "highpotential",
                  "hipo", "potentialseverity", "seriouspotential"],
    "severity": ["severity", "actualseverity", "consequence", "injurylevel",
                 "riskrating", "severitylevel"],
    "status": ["status", "reviewstatus", "state", "workflowstatus", "disposition"],
}

# Truthy strings for a SIF label column.
_TRUE = {"1", "yes", "y", "true", "sif", "sifpotential", "sif-potential", "high",
         "hipo", "highpotential", "serious", "potential", "t"}
_FALSE = {"0", "no", "n", "false", "nonsif", "non-sif", "nonsifpotential", "low",
          "notsif", "none", "f"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@dataclass
class LoadResult:
    frame: pd.DataFrame
    mapping: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    rows_in: int = 0
    rows_out: int = 0
    unmapped_columns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "mapping": self.mapping,
            "warnings": self.warnings,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "unmapped_columns": self.unmapped_columns,
        }


class DataLoadError(Exception):
    """Raised with an operator-readable message; never surfaced as a traceback."""


def _score_column(col: str, aliases: list[str]) -> int:
    """Higher is better. Exact alias beats prefix beats substring."""
    n = _norm(col)
    if not n:
        return 0
    best = 0
    for a in aliases:
        if n == a:
            best = max(best, 100)
        elif n.startswith(a) or n.endswith(a):
            best = max(best, 70 - abs(len(n) - len(a)))
        elif a in n:
            best = max(best, 45 - abs(len(n) - len(a)))
    return max(best, 0)


def infer_mapping(df: pd.DataFrame) -> tuple[dict[str, str], list[str]]:
    """Map canonical fields to actual columns by name, then by content."""
    warnings: list[str] = []
    mapping: dict[str, str] = {}
    taken: set[str] = set()

    # Name-based, best match wins, each source column used once.
    candidates: list[tuple[int, str, str]] = []
    for canonical, aliases in COLUMN_ALIASES.items():
        for col in df.columns:
            s = _score_column(col, aliases)
            if s > 0:
                candidates.append((s, canonical, col))
    for score, canonical, col in sorted(candidates, key=lambda x: -x[0]):
        if canonical in mapping or col in taken:
            continue
        mapping[canonical] = col
        taken.add(col)

    # Content-based fallback for the one field we cannot do without.
    #
    # Deliberately does NOT test for `dtype == object`: pandas 3.0 gives string
    # columns a dedicated `str` dtype, so an object-only check silently skips
    # every text column and the fallback never fires. We just measure length.
    if "narrative" not in mapping:
        best_col, best_len = None, 0
        for col in df.columns:
            if col in taken:
                continue
            try:
                values = df[col].dropna().astype(str)
            except (TypeError, ValueError):
                continue
            if values.empty:
                continue
            # A narrative column is prose, not an identifier or a code.
            avg = float(values.str.len().mean())
            if avg > best_len:
                best_col, best_len = col, avg
        if best_col is not None and best_len >= 40:
            mapping["narrative"] = best_col
            taken.add(best_col)
            warnings.append(
                f"No column named like a narrative; using '{best_col}' "
                f"(longest average text, {best_len:.0f} chars)."
            )

    return mapping, warnings


def _coerce_sif(series: pd.Series) -> pd.Series:
    def one(v):
        if pd.isna(v):
            return pd.NA
        s = _norm(v)
        if s in _TRUE:
            return 1
        if s in _FALSE:
            return 0
        try:
            f = float(v)
            return 1 if f >= 0.5 else 0
        except (TypeError, ValueError):
            return pd.NA

    return series.map(one).astype("Int64")


def read_csv(source, filename: str = "uploaded.csv") -> pd.DataFrame:
    """Read a CSV from a path, bytes or file-like, tolerating common encodings."""
    if isinstance(source, (bytes, bytearray)):
        last: Exception | None = None
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(source), encoding=enc, dtype=str,
                                   keep_default_na=False, na_values=[""], on_bad_lines="skip")
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                last = e
        raise DataLoadError(f"Could not decode '{filename}'. Save it as UTF-8 CSV. ({last})")

    try:
        return pd.read_csv(source, dtype=str, keep_default_na=False,
                           na_values=[""], on_bad_lines="skip", encoding_errors="replace")
    except FileNotFoundError:
        raise DataLoadError(f"File not found: {source}")
    except pd.errors.EmptyDataError:
        raise DataLoadError(f"'{filename}' is empty - no columns or rows found.")
    except pd.errors.ParserError as e:
        raise DataLoadError(f"'{filename}' is not valid CSV: {e}")


def load(source, filename: str = "uploaded.csv",
         override: dict[str, str] | None = None) -> LoadResult:
    """
    Load and normalise a safety-report CSV into the canonical schema.

    `override` lets the column-mapping UI correct any inference.
    """
    df = read_csv(source, filename)
    rows_in = len(df)

    if df.empty:
        raise DataLoadError(f"'{filename}' contains no data rows.")

    df.columns = [str(c).strip() for c in df.columns]
    mapping, warnings = infer_mapping(df)
    if override:
        for k, v in override.items():
            if v and v in df.columns:
                mapping[k] = v

    if "narrative" not in mapping:
        raise DataLoadError(
            "No free-text narrative column could be identified. "
            f"Columns found: {', '.join(map(str, df.columns[:12]))}. "
            "Use the column mapping controls to point at the description field."
        )

    out = pd.DataFrame(index=df.index)
    for canonical in COLUMN_ALIASES:
        src = mapping.get(canonical)
        out[canonical] = df[src] if src in df.columns else pd.NA

    out["narrative"] = out["narrative"].fillna("").astype(str).str.strip()
    blank = (out["narrative"].str.len() < 15).sum()
    if blank:
        warnings.append(f"Dropped {blank} row(s) with no usable narrative text.")
        out = out[out["narrative"].str.len() >= 15]

    if out.empty:
        raise DataLoadError(
            "Every row was dropped: no row had a narrative of at least 15 characters."
        )

    # Dates: parse leniently, keep NaT rather than guessing.
    parsed = pd.to_datetime(out["date"], errors="coerce", format="mixed", dayfirst=True)
    if parsed.notna().sum() == 0 and out["date"].notna().sum() > 0:
        warnings.append("Date column could not be parsed; time filters will be unavailable.")
    out["date"] = parsed

    if out["sif_label"].notna().any():
        out["sif_label"] = _coerce_sif(out["sif_label"])
        n_lab = int(out["sif_label"].notna().sum())
        warnings.append(
            f"Found verified SIF labels on {n_lab} row(s); these will be used for validation metrics."
        )
    else:
        out["sif_label"] = pd.Series([pd.NA] * len(out), dtype="Int64")

    for col, default in (
        ("location", "Unspecified"),
        ("asset", "Unspecified"),
        ("report_type", "Unspecified"),
        ("status", "Pending Review"),
    ):
        out[col] = out[col].fillna(default).replace("", default)

    if mapping.get("report_id"):
        out["report_id"] = out["report_id"].fillna("").astype(str).str.strip()
    missing_id = out["report_id"].isna() | (out["report_id"].astype(str).str.len() == 0)
    if missing_id.any():
        out.loc[missing_id, "report_id"] = [
            f"R-{i:06d}" for i in range(1, int(missing_id.sum()) + 1)
        ]
    dupes = out["report_id"].duplicated()
    if dupes.any():
        warnings.append(f"Made {int(dupes.sum())} duplicate report ID(s) unique.")
        out.loc[dupes, "report_id"] = out.loc[dupes, "report_id"].astype(str) + "-" + [
            str(i) for i in range(1, int(dupes.sum()) + 1)
        ]

    # Preserve provenance columns when the corpus builder supplied them.
    for extra in ("narrative_provenance", "context_provenance", "sector_provenance",
                  "sif_label_reason", "data_source"):
        if extra in df.columns:
            out[extra] = df[extra]

    unmapped = [c for c in df.columns if c not in set(mapping.values())]
    return LoadResult(
        frame=out.reset_index(drop=True),
        mapping=mapping,
        warnings=warnings,
        rows_in=rows_in,
        rows_out=len(out),
        unmapped_columns=unmapped,
    )
