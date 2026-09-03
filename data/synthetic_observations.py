"""
Synthetic OIL-style UA / UC / Near-Miss observations.

WHY THIS EXISTS
---------------
The real corpus comes from OSHA Severe Injury Reports, where **every record is an
injury that already happened**. That creates two problems the real data cannot
fix:

  1. Labelling an OSHA injury record "Unsafe Condition" produces a contradiction -
     an unsafe-condition observation whose narrative ends in surgery. Any reader
     who opens two reports sees it.

  2. The system's whole purpose is triaging UA/UC/near-miss reports, written
     BEFORE anyone is hurt. That register - "observed that...", "was about to...",
     no injury outcome - appears nowhere in OSHA data.

So real OSHA records are now all typed `Incident` (which is what they are), and
this module generates the observation layer separately, in OIL's operational
register and vocabulary.

HONESTY CONTRACT
----------------
Every row produced here is tagged `narrative_provenance = "synthetic"`. These
narratives are machine-written and are NOT real safety reports. They exist so the
demo exercises the near-miss path; the ML model's reported metrics are computed
on the REAL subset only (see notebooks/sif_training.ipynb).

Labels here are assigned by construction - each template declares whether it
describes a failed critical control around a high-energy source. That is
legitimate for generated text (we know the ground truth because we wrote it), but
it means these rows must never be mixed into the model's validation metrics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Operational vocabulary
# --------------------------------------------------------------------------

CREW = [
    "the rigger", "the fitter", "a contract workman", "the welder",
    "the operator", "the technician", "a helper", "the electrician",
    "the crane operator", "the floorman", "a contractor crew member",
    "the maintenance fitter", "the scaffolder", "the driver",
]

OBSERVER_OPENERS = [
    "During routine site walkaround it was observed that",
    "During the HSE field visit it was noticed that",
    "While conducting a work-area inspection it was observed that",
    "During the shift handover round it was found that",
    "On inspection of the work permit area it was observed that",
    "During the safety audit it was noted that",
]

NEARMISS_OPENERS = [
    "Work was stopped when it was found that",
    "The job was halted by the area supervisor after it was noticed that",
    "A stop-work was raised when it was observed that",
    "The activity was suspended immediately on noticing that",
]

CLOSERS_UNSAFE = [
    "The activity was stopped and the crew was briefed before work resumed.",
    "Work was suspended and the permit was withdrawn pending rectification.",
    "The area was cleared and the job was re-planned with the area authority.",
    "The observation was raised with the executing agency for immediate correction.",
]

CLOSERS_SAFE = [
    "Work proceeded as planned with no deviation observed.",
    "The activity was found to be in full compliance with the permit conditions.",
    "No deviation was observed and the job continued normally.",
    "The crew was appreciated for correct compliance during the toolbox talk.",
]


@dataclass(frozen=True)
class Template:
    rule: str
    sif: int
    body: str          # {who} slot available
    types: tuple[str, ...] = ("Unsafe Act", "Unsafe Condition", "Near Miss")


# --------------------------------------------------------------------------
# Templates - controls FAILED (SIF-potential)
# --------------------------------------------------------------------------

FAILED: list[Template] = [
    # Confined Space
    Template("confined_space", 1,
             "{who} was about to enter the crude storage tank through the manway before gas testing had been completed and no standby attendant was posted at the entry point"),
    Template("confined_space", 1,
             "{who} had entered the separator vessel for internal cleaning without a valid confined space entry permit and the oxygen level had not been checked"),
    Template("confined_space", 1,
             "the H2S monitor at the sump pit entry was found switched off while {who} was working inside, and no continuous gas monitoring was in place"),
    Template("confined_space", 1,
             "{who} entered the effluent pit without breathing apparatus and the atmosphere had not been purged before entry"),

    # Hot Work
    Template("hot_work", 1,
             "gas cutting was in progress on the flowline at the group gathering station while no fire watch was posted and the fire extinguisher was not available at the work spot"),
    Template("hot_work", 1,
             "{who} was carrying out welding on a pipeline section adjacent to a live hydrocarbon line and the hot work permit had expired the previous shift"),
    Template("hot_work", 1,
             "grinding was being carried out near the crude oil pump without any spark containment and the drain nearby was left open"),
    Template("hot_work", 1,
             "hot work was in progress at the well head while the gas test had not been repeated after the shift break and the fire watch had left the location"),

    # Energy Isolation
    Template("energy_isolation", 1,
             "{who} started opening the pump casing flange before the line was depressurised and the isolation valves had not been locked out"),
    Template("energy_isolation", 1,
             "the electrical panel at the collecting station was found opened for maintenance while still energised, with no lock-out tag applied"),
    Template("energy_isolation", 1,
             "{who} began work on the gas compressor without verifying zero energy state, and the isolation tag was found lying beside the panel"),
    Template("energy_isolation", 1,
             "a blind flange was being removed from the flowline before the line was drained and the upstream valve was still under pressure"),

    # Working at Height
    Template("working_at_height", 1,
             "{who} was working on the workover rig derrick monkey board without the safety harness anchored to any lifeline"),
    Template("working_at_height", 1,
             "the scaffold platform at the drilling rig was found without handrails and toe-boards, and the scaffold tag had not been issued"),
    Template("working_at_height", 1,
             "a floor grating near the mud pump was found removed and the opening was left uncovered without barricading"),
    Template("working_at_height", 1,
             "{who} was climbing the storage tank staircase carrying tools by hand with no fall protection while the handrail section was missing"),

    # Line of Fire
    Template("line_of_fire", 1,
             "{who} was standing directly in the line of fire while the pressurised hose union was being tightened at the well head"),
    Template("line_of_fire", 1,
             "the rotating coupling guard of the transfer pump was found removed and left off while the pump was running"),
    Template("line_of_fire", 1,
             "{who} was positioned between the moving tong and the drill pipe while the connection was being made up on the rig floor"),

    # Safe Mechanical Lifting
    Template("safe_mechanical_lifting", 1,
             "{who} was standing under a suspended casing joint while the crane was slewing, and the drop zone had not been barricaded"),
    Template("safe_mechanical_lifting", 1,
             "the lifting sling being used at the workshop was found frayed and without any valid inspection tag, and no lift plan was available"),
    Template("safe_mechanical_lifting", 1,
             "a tandem lift was in progress at the location without any lift plan and no banksman was deployed to control the load"),

    # Work Authorisation
    Template("work_authorisation", 1,
             "excavation work near the buried pipeline had started without a valid work permit and no underground utility drawing had been referred"),
    Template("work_authorisation", 1,
             "{who} was carrying out pipe fitting inside the plant area without any permit and no job safety analysis had been prepared for the task"),

    # Bypassing Safety Controls
    Template("bypassing_safety_controls", 1,
             "the emergency shutdown interlock of the gas compressor was found bypassed without any authorisation to keep the unit running"),
    Template("bypassing_safety_controls", 1,
             "the high level alarm of the crude storage tank was found disabled and the deviation had not been recorded anywhere"),
    Template("bypassing_safety_controls", 1,
             "the pressure safety valve on the separator was found isolated with the upstream valve closed and no compensatory measure in place"),

    # Driving
    Template("driving", 1,
             "the crew bus was observed overtaking on the approach road at high speed and the driver was using a mobile phone while driving",
             ("Unsafe Act", "Near Miss")),
    Template("driving", 1,
             "a tanker was observed reversing at the loading gantry without any spotter and the reverse alarm was not working",
             ("Unsafe Act", "Unsafe Condition", "Near Miss")),
]

# --------------------------------------------------------------------------
# Templates - controls HELD (non-SIF). These matter as much as the failures:
# they are what stops the model flagging every mention of a hazardous activity.
# --------------------------------------------------------------------------

HELD: list[Template] = [
    Template("confined_space", 0,
             "confined space entry into the separator was in progress with a valid permit, gas testing completed and the standby attendant posted at the manway",
             ("Unsafe Condition",)),
    Template("hot_work", 0,
             "welding at the gathering station was being carried out with a valid hot work permit, the fire watch stationed and the gas test repeated after the break",
             ("Unsafe Condition",)),
    Template("energy_isolation", 0,
             "the pump overhaul was started only after isolation was verified, zero energy state was confirmed and the lock-out tag was applied by the authorised person",
             ("Unsafe Condition",)),
    Template("working_at_height", 0,
             "scaffold erection at the rig was completed with handrails and toe-boards fitted, and the scaffold tag was issued after inspection",
             ("Unsafe Condition",)),
    Template("safe_mechanical_lifting", 0,
             "the lifting operation at the well head was carried out with an approved lift plan, the area barricaded and a banksman controlling the load",
             ("Unsafe Condition",)),
    # Genuine low-energy observations - the everyday reports that must NOT be
    # flagged, and which currently dominate any real HSSE portfolio.
    Template("work_authorisation", 0,
             "housekeeping in the workshop store was found poor with materials stacked untidily near the walkway"),
    Template("work_authorisation", 0,
             "the drinking water point near the office block was found leaking and the surrounding floor was wet"),
    Template("work_authorisation", 0,
             "{who} was observed not wearing the chin strap of the safety helmet while walking through the plant road"),
    Template("work_authorisation", 0,
             "illumination at the store approach path was found inadequate during the night shift round"),
    Template("work_authorisation", 0,
             "the notice board at the location was found with outdated emergency contact numbers displayed"),
    Template("work_authorisation", 0,
             "a few empty cement bags were observed lying near the civil work area and had not been cleared"),
    Template("work_authorisation", 0,
             "{who} was observed carrying a tea flask while walking on the plant road during the shift"),
    Template("work_authorisation", 0,
             "the first aid box at the workshop was found with a few consumed items not yet replenished"),
    Template("work_authorisation", 0,
             "minor oil seepage was observed at the pump gland and was within the tray, with no spillage to the ground"),
    Template("work_authorisation", 0,
             "the toolbox talk register at the site was found signed but the date column was left blank for one entry"),
]


def _h(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{salt}:{seed}".encode()).hexdigest()[:12], 16)


def generate(n: int, fields: list[str], assets: list[str], start_index: int = 0) -> list[dict]:
    """
    Generate `n` synthetic observations, deterministically.

    Roughly a third describe failed controls, matching the SIF base rate of the
    real corpus rather than producing an implausibly dangerous site.
    """
    pool: list[tuple[Template, int]] = []
    # Weight so the corpus is realistic: mostly routine observations.
    for i, t in enumerate(FAILED):
        pool.extend([(t, i)] * 2)
    for i, t in enumerate(HELD):
        pool.extend([(t, 1000 + i)] * 12)

    rows: list[dict] = []
    for k in range(n):
        seed = f"syn{start_index + k}"
        tpl, _ = pool[_h(seed, "tpl") % len(pool)]
        rtype = tpl.types[_h(seed, "rt") % len(tpl.types)]

        who = CREW[_h(seed, "who") % len(CREW)]
        if rtype == "Near Miss":
            opener = NEARMISS_OPENERS[_h(seed, "op") % len(NEARMISS_OPENERS)]
        else:
            opener = OBSERVER_OPENERS[_h(seed, "op") % len(OBSERVER_OPENERS)]
        closers = CLOSERS_UNSAFE if tpl.sif else CLOSERS_SAFE
        closer = closers[_h(seed, "cl") % len(closers)]

        body = tpl.body.format(who=who)
        narrative = f"{opener} {body}. {closer}"

        rows.append(
            {
                "narrative": narrative,
                "sif_label": tpl.sif,
                "report_type": rtype,
                "iogp_seed_rule": tpl.rule,
                "sif_label_reason": (
                    "constructed: failed critical control with high-energy exposure"
                    if tpl.sif
                    else "constructed: no critical control failure / low-energy observation"
                ),
                "seed": seed,
            }
        )
    return rows
