"""
Behavioural tests for the SIF-Trace engine.

These are not coverage tests. Each one pins a behaviour that, if it broke,
would make the system wrong in a way a demo would not reveal - most importantly
the distinction between a control that HELD and a control that FAILED.

    ../.venv/Scripts/python -m pytest tests/ -v      (run from backend/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sif import knowledge as kb
from sif.data_loader import DataLoadError, load
from sif.iogp_mapper import map_rule
from sif.precursor_extractor import extract
from sif.risk_engine import relative_density_level
from sif.sif_classifier import mask_outcome, rule_score


# --------------------------------------------------------------------------
# The central discrimination: did the control hold, or did it fail?
# --------------------------------------------------------------------------

CONTROLS_FAILED = [
    "Worker entered confined space without gas testing and permit verification.",
    "Worker entered confined space without gas testing or permit.",
    "Technician entered a confined space before gas testing was completed.",
    "The permit to work was valid but the fire watch had not been arranged.",
    "Hot work started although the gas test was not completed and no fire watch was posted.",
    "Operator bypassed the ESD interlock without authorisation to keep the compressor running.",
    "Pump coupling guard was found removed and left off while the pump was running.",
    "Floor grating cover had been taken off and was not replaced, leaving an open hole.",
    "Handrail was removed for maintenance and not re-fitted on the elevated walkway.",
]

CONTROLS_HELD = [
    "Maintenance started after confirming isolation and zero-energy state.",
    "Confined space permit was valid and gas testing was completed before entry.",
    "Lift plan was approved, the area was barricaded and a banksman was stationed.",
    "Machine guard was refitted and verified before the pump was restarted.",
    "Scaffold handrail and toe-boards were installed and inspected before work began.",
]


@pytest.mark.parametrize("text", CONTROLS_FAILED)
def test_failed_controls_produce_precursors(text):
    result = extract(text)
    assert result.failed_barriers, f"expected a failed barrier in: {text}"
    assert result.precursor_labels(), f"expected precursors in: {text}"


@pytest.mark.parametrize("text", CONTROLS_HELD)
def test_held_controls_produce_no_precursors(text):
    """
    The false-alarm test. A job done correctly must never be flagged, or HSE
    teams stop trusting the system.
    """
    result = extract(text)
    assert not result.failed_barriers, (
        f"false alarm - reported a failed barrier for compliant work: {text} "
        f"-> {[b.canonical for b in result.failed_barriers]}"
    )
    assert not result.precursor_labels(), f"false precursor for: {text}"


def test_contrastive_clause_resolves_two_opposite_statuses():
    """One sentence, one control that held and one that failed."""
    r = extract("The permit to work was valid but the fire watch had not been arranged.")
    failed = {b.key for b in r.failed_barriers}
    present = {b.key for b in r.present_barriers}
    assert "fire_watch" in failed
    assert "permit_to_work" in present


def test_ordering_cue_only_counts_on_the_left():
    """
    "entered before gas testing was completed"  -> control came too late
    "gas testing was completed before entry"    -> compliant
    """
    late = extract("Technician entered the vessel before gas testing was completed.")
    fine = extract("Gas testing was completed before entry into the vessel.")
    assert any(b.key == "gas_testing" for b in late.failed_barriers)
    assert not any(b.key == "gas_testing" for b in fine.failed_barriers)


# --------------------------------------------------------------------------
# IOGP mapping
# --------------------------------------------------------------------------

SPEC_MAPPINGS = [
    ("equipment not isolated before maintenance", "Energy Isolation"),
    ("entered confined vessel without gas test", "Confined Space"),
    ("hot work performed without fire watch", "Hot Work"),
    ("worker standing under suspended load", "Safe Mechanical Lifting"),
    ("work started without valid permit", "Work Authorisation"),
    ("working on elevated platform without fall protection", "Working at Height"),
    ("critical interlock bypassed without authorization", "Bypassing Safety Controls"),
    ("vehicle speeding on lease road, unsafe driving observed", "Driving"),
]


@pytest.mark.parametrize("text,expected", SPEC_MAPPINGS)
def test_iogp_rule_mapping(text, expected):
    assert map_rule(text, extract(text)).rule_name == expected


def test_unmappable_report_returns_none_not_a_guess():
    m = map_rule("Employee reported the canteen was closed.", extract("Employee reported the canteen was closed."))
    assert m.rule is None
    assert "could be mapped" in m.explain()
    assert "Manual HSE classification is required" in m.explain()


def test_mapping_explanation_is_human_readable():
    text = "Hot work was carried out without a fire watch."
    m = map_rule(text, extract(text))
    explanation = m.explain()
    assert "Hot Work" in explanation
    assert "because" in explanation


# --------------------------------------------------------------------------
# Outcome masking
# --------------------------------------------------------------------------


def test_outcome_words_are_masked():
    masked = mask_outcome("his finger was amputated and he was hospitalized")
    assert "amputat" not in masked.lower()
    assert "hospitali" not in masked.lower()


def test_masking_preserves_circumstance_words():
    """Masking must remove the consequence but keep the precursor context."""
    masked = mask_outcome(
        "Employee was descending the workover rig derrick when he fell and fractured his hip."
    )
    for keep in ("workover", "rig", "derrick", "descending"):
        assert keep in masked.lower(), f"masking destroyed circumstance word: {keep}"


# --------------------------------------------------------------------------
# Scoring behaviour
# --------------------------------------------------------------------------


def test_hazard_alone_does_not_reach_sif_threshold():
    """
    Routine work around a high-energy source is not a precursor. Only a hazard
    PLUS a failed control is.
    """
    r = extract("Technician carried out a routine inspection of the high voltage panel.")
    assert rule_score(r) < 0.5


def test_multiple_failed_barriers_score_higher_than_one():
    one = extract("Hot work was carried out without a fire watch.")
    many = extract(
        "Hot work was carried out without a fire watch, without a permit, "
        "and the gas test had expired."
    )
    assert rule_score(many) > rule_score(one)


# --------------------------------------------------------------------------
# Density ranking
# --------------------------------------------------------------------------


def test_small_sample_is_not_flagged_critical():
    """A site with 2 reports and 1 SIF must not top the ranking at 50% density."""
    level, ratio, z = relative_density_level(1, 2, baseline=0.25)
    assert ratio > 1.4          # the raw ratio looks alarming
    assert level != "Critical"  # but it is not statistically significant
    assert z < 1.64


def test_large_sample_above_baseline_is_flagged():
    level, ratio, z = relative_density_level(160, 400, baseline=0.25)
    assert level in ("High", "Critical")
    assert z >= 1.64


def test_below_baseline_is_low_even_with_many_reports():
    """The count-vs-density inversion the spec requires."""
    level, _, _ = relative_density_level(200, 1000, baseline=0.25)
    assert level == "Low"


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------


def test_column_mapping_survives_unfamiliar_names(tmp_path):
    csv = tmp_path / "odd.csv"
    csv.write_text(
        "Sr No,Reported On,Installation,Job Being Done,What Was Observed\n"
        "1,15-03-2025,Moran,Welding,"
        '"Welder was cutting on a flowline while no fire watch was present."\n',
        encoding="utf-8",
    )
    res = load(csv, "odd.csv")
    assert res.mapping["narrative"] == "What Was Observed"
    assert res.mapping["location"] == "Installation"
    assert res.rows_out == 1


def test_narrative_found_by_content_when_name_is_meaningless(tmp_path):
    csv = tmp_path / "blind.csv"
    csv.write_text(
        "aaa,bbb\n"
        "X1,"
        '"The technician entered the separator vessel before the gas test had been completed, '
        'and no standby attendant was posted at the manway."\n',
        encoding="utf-8",
    )
    res = load(csv, "blind.csv")
    assert res.mapping["narrative"] == "bbb"
    assert any("longest average text" in w for w in res.warnings)


def test_header_only_file_raises_readable_error(tmp_path):
    csv = tmp_path / "empty.csv"
    csv.write_text("a,b\n", encoding="utf-8")
    with pytest.raises(DataLoadError) as exc:
        load(csv, "empty.csv")
    assert "no data rows" in str(exc.value).lower()


def test_file_without_narrative_raises_readable_error(tmp_path):
    csv = tmp_path / "nonarr.csv"
    csv.write_text("code,qty\nA1,5\nB2,7\n", encoding="utf-8")
    with pytest.raises(DataLoadError) as exc:
        load(csv, "nonarr.csv")
    assert "narrative" in str(exc.value).lower()


# --------------------------------------------------------------------------
# Knowledge base integrity
# --------------------------------------------------------------------------


def test_every_barrier_and_hazard_points_at_a_real_rule():
    for key, spec in kb.BARRIERS.items():
        assert spec["rule"] in kb.IOGP_RULES, f"{key} -> unknown rule {spec['rule']}"
    for key, spec in kb.HAZARDS.items():
        assert spec["rule"] in kb.IOGP_RULES, f"{key} -> unknown rule {spec['rule']}"


def test_all_nine_life_saving_rules_present():
    assert len(kb.IOGP_RULES) == 9


def test_activity_maps_are_complete():
    assert set(kb.ACTIVITY_IMPLIED_HAZARDS) == set(kb.ACTIVITIES)
    assert set(kb.EXPOSURE_TEMPLATES) == set(kb.ACTIVITIES)


def test_barrier_failure_labels_normalise_surface_variants():
    """
    The spec requires "fire watcher absent" / "no fire watch" / "firewatch
    missing" to collapse to one concept.
    """
    variants = [
        "Hot work proceeded but the fire watcher was absent.",
        "Hot work proceeded with no fire watch.",
        "Hot work proceeded, firewatch missing.",
        "Hot work proceeded and the fire watch was not available.",
    ]
    labels = set()
    for v in variants:
        for b in extract(v).failed_barriers:
            if b.key == "fire_watch":
                labels.add(b.canonical)
    assert labels == {"Fire Watch Missing"}, labels
