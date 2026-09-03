"""
SIF-Trace safety knowledge base.

Everything domain-specific lives here so HSE professionals can extend the system
without touching pipeline code:

  * IOGP_RULES        - the nine IOGP Life-Saving Rules
  * BARRIERS          - critical control concepts + how they surface in free text
  * FAILURE_CUES      - language indicating a control was absent/bypassed/late
  * PRESENCE_CUES     - language indicating a control was correctly applied
  * HAZARDS           - energy/exposure sources with fatal potential
  * ACTIVITIES        - work activity taxonomy
  * SEVERITY_CUES     - outcome language implying high-consequence exposure

Design note on the central NLP problem
--------------------------------------
A keyword alone is meaningless. "Confined space permit was valid and gas testing
was completed" and "entered the confined space without gas testing" share almost
all their vocabulary. What separates them is whether the barrier language appears
in a FAILURE context or a PRESENCE context.

So every barrier is modelled as (trigger, status), where status is resolved from
cue words in a window around the trigger, plus ordering cues ("before testing was
completed") which imply the control came too late.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# IOGP Life-Saving Rules (IOGP Report 459)
# --------------------------------------------------------------------------

IOGP_RULES: dict[str, dict] = {
    "bypassing_safety_controls": {
        "name": "Bypassing Safety Controls",
        "icon": "shield-off",
        "statement": "Obtain authorisation before overriding or disabling safety controls.",
        "description": (
            "Covers defeating, disabling, overriding or ignoring engineered safety "
            "devices - interlocks, trips, alarms, ESD systems, relief protection - "
            "without formal authorisation and compensatory measures."
        ),
    },
    "confined_space": {
        "name": "Confined Space",
        "icon": "box",
        "statement": "Obtain authorisation before entering a confined space.",
        "description": (
            "Covers entry into vessels, tanks, pits, sumps, excavations and other "
            "spaces with restricted egress, where the atmosphere may be "
            "oxygen-deficient, flammable or toxic."
        ),
    },
    "driving": {
        "name": "Driving",
        "icon": "truck",
        "statement": "Follow safe driving rules.",
        "description": (
            "Covers journey management, speed, seatbelts, fatigue, mobile phone use "
            "and vehicle condition for light and heavy vehicles."
        ),
    },
    "energy_isolation": {
        "name": "Energy Isolation",
        "icon": "zap-off",
        "statement": "Verify isolation and zero energy before work begins.",
        "description": (
            "Covers lock-out/tag-out, positive isolation, de-pressurisation, draining, "
            "purging and proving zero energy before breaking containment or working "
            "on equipment."
        ),
    },
    "hot_work": {
        "name": "Hot Work",
        "icon": "flame",
        "statement": "Control flammables and ignition sources.",
        "description": (
            "Covers welding, cutting, grinding, burning and any spark-producing work "
            "in areas where flammable vapour or gas may be present."
        ),
    },
    "line_of_fire": {
        "name": "Line of Fire",
        "icon": "crosshair",
        "statement": "Keep yourself and others out of the line of fire.",
        "description": (
            "Covers exposure to released energy - suspended loads, pressurised "
            "release, moving or rotating equipment, stored energy, vehicle movement "
            "and pinch points."
        ),
    },
    "safe_mechanical_lifting": {
        "name": "Safe Mechanical Lifting",
        "icon": "move-vertical",
        "statement": "Plan lifting operations and control the area.",
        "description": (
            "Covers cranes, hoists, slings, rigging, lift plans, load integrity and "
            "exclusion zones around lifting operations."
        ),
    },
    "work_authorisation": {
        "name": "Work Authorisation",
        "icon": "clipboard-check",
        "statement": "Work with a valid permit when required.",
        "description": (
            "Covers the permit-to-work system, risk assessment, toolbox talks, job "
            "safety analysis and formal authorisation before high-hazard work."
        ),
    },
    "working_at_height": {
        "name": "Working at Height",
        "icon": "arrow-up-from-line",
        "statement": "Protect yourself against a fall when working at height.",
        "description": (
            "Covers fall arrest and restraint, scaffolding, ladders, derrick and mast "
            "work, elevated platforms, and floor or roof openings."
        ),
    },
}

RULE_ORDER = list(IOGP_RULES.keys())


# --------------------------------------------------------------------------
# Cue vocabularies used for context resolution
# --------------------------------------------------------------------------

# Language indicating a control was MISSING, BYPASSED, EXPIRED or LATE.
FAILURE_CUES: list[str] = [
    r"without",
    r"with\s+no",
    r"lack(?:ing|ed|s)?(?:\s+of)?",
    r"absen(?:t|ce)",
    r"missing",
    r"not\s+(?:been\s+)?(?:available|present|used|worn|done|carried\s+out|performed|conducted|completed|obtained|taken|closed|in\s+place|fitted|installed|isolated|tested|verified|checked)",
    r"never\s+(?:been\s+)?\w+",
    r"fail(?:ed|ure|ing|s)?\s+to",
    r"failure\s+of",
    r"did\s+not",
    r"didn.?t",
    r"was\s+not",
    r"were\s+not",
    r"had\s+not",
    r"has\s+not",
    r"is\s+not",
    r"are\s+not",
    r"bypass(?:ed|ing|es)?",
    r"by-?passed",
    r"overrid(?:e|den|ing)",
    r"override",
    r"defeat(?:ed|ing)?",
    r"disabl(?:ed|ing)",
    r"deactivat(?:ed|ing)",
    r"jumped\s+out",
    r"blocked\s+open",
    r"tied\s+(?:back|open)",
    r"ignor(?:ed|ing)",
    r"neglect(?:ed|ing)?",
    r"omitt?(?:ed|ing)",
    r"skipp?(?:ed|ing)",
    r"expired",
    r"out\s+of\s+date",
    r"invalid",
    r"unauthoris(?:ed)?",
    r"unauthoriz(?:ed)?",
    r"non-?compliant",
    r"incomplete",
    r"improper(?:ly)?",
    r"inadequate",
    r"insufficient",
    r"unprotected",
    r"unguarded",
    r"unsecured",
    r"uncontrolled",
    r"unattended",
    r"un-?isolated",
    r"still\s+(?:pressuris|pressuriz|energis|energiz|charged|live|running|rotating)\w*",
    r"prior\s+to",
    r"before\s+\w+\s+(?:was|were|had|could)",
    r"before\s+(?:completing|completion|testing|isolation|obtaining)",
    r"yet\s+to\s+be",
    r"not\s+yet",
    r"defective",
    r"damaged",
    r"faulty",
    r"malfunction\w*",
    r"proceed(?:ed)?\s+(?:anyway|without)",
    r"continued\s+(?:anyway|without)",
    # Physical removal of a control. Guards, covers, railings and blanks are
    # rarely described as "missing" - the reporter writes that someone took them
    # off and did not put them back.
    r"remov(?:ed|al|ing)",
    r"taken\s+off",
    r"left\s+off",
    r"left\s+open",
    r"not\s+replaced",
    r"not\s+re-?fitted",
    r"not\s+re-?installed",
    r"not\s+put\s+back",
    r"dismantl(?:ed|ing)",
    r"lying\s+(?:on|beside)",
    r"lifted\s+off",
    r"unbolted",
    r"loose",
]

# Language indicating a control WAS correctly applied. Guards against false positives.
PRESENCE_CUES: list[str] = [
    r"valid",
    r"in\s+place",
    r"in\s+force",
    r"obtained",
    r"secured",
    r"completed",
    r"conducted",
    r"carried\s+out",
    r"performed",
    r"verified",
    r"confirm(?:ed|ing)?",
    r"validated",
    r"certified",
    r"approved",
    r"authoris(?:ed)?",
    r"authoriz(?:ed)?",
    r"signed(?:\s+off)?",
    r"endorsed",
    r"ensur(?:ed|ing)",
    r"check(?:ed)?",
    r"inspect(?:ed)?",
    r"tested\s+(?:clear|safe|satisfactory)",
    r"satisfactory",
    r"clear(?:ed)?",
    r"safe\s+(?:limits|levels|atmosphere)",
    r"applied",
    r"fitted",
    r"installed",
    r"worn",
    r"used\s+correctly",
    r"properly\s+\w+",
    r"correctly\s+\w+",
    r"as\s+per\s+procedure",
    r"in\s+accordance\s+with",
    r"present",
    r"available",
    r"attend(?:ed|ing|ance)",
    r"stationed",
    r"posted",
    r"zero\s+energy\s+(?:state\s+)?(?:confirmed|verified|established|achieved)",
    r"after\s+(?:confirming|verifying|completing|isolating|obtaining|testing)",
    r"following\s+(?:confirmation|verification|completion|isolation)",
    r"successfully",
    r"compliant",
    r"adequate",
    r"effective",
]

# Words that flip a following PRESENCE cue: "not completed", "no valid permit".
PRESENCE_NEGATORS: list[str] = [
    r"not",
    r"no",
    r"never",
    r"without",
    r"nor",
    r"neither",
    r"failed\s+to",
    r"unable\s+to",
    r"lack\w*",
    r"absent",
    r"missing",
]


# --------------------------------------------------------------------------
# Critical barriers (controls). Each maps to the IOGP rule it protects.
# --------------------------------------------------------------------------

BARRIERS: dict[str, dict] = {
    "permit_to_work": {
        "label": "Permit to Work",
        "rule": "work_authorisation",
        "triggers": [
            r"permits?(?:\s+to\s+work)?",
            r"\bptw\b",
            r"work\s+permits?",
            r"hot\s+work\s+permits?",
            r"entry\s+permits?",
            r"clearance\s+certificates?",
            r"work\s+authoris(?:ation)?",
            r"work\s+authoriz(?:ation)?",
        ],
        "weight": 0.9,
    },
    "risk_assessment": {
        "label": "Risk Assessment / JSA",
        "rule": "work_authorisation",
        "triggers": [
            r"\bjsa\b",
            r"\bjha\b",
            r"risk\s+assessment",
            r"job\s+safety\s+analysis",
            r"toolbox\s+talks?",
            r"tool\s?box\s+meetings?",
            r"method\s+statements?",
            r"pre-?job\s+(?:brief|discussion|meeting)",
            r"safety\s+briefings?",
        ],
        "weight": 0.6,
    },
    "gas_testing": {
        "label": "Gas Testing / Atmospheric Monitoring",
        "rule": "confined_space",
        "triggers": [
            r"gas\s+tests?(?:ing)?",
            r"gas\s+detect\w*",
            r"gas\s+monitor\w*",
            r"atmospheric\s+(?:test\w*|monitor\w*|check\w*)",
            r"oxygen\s+(?:level|test|content|check)\w*",
            r"\blel\b",
            r"h2s\s+(?:test|monitor|detect)\w*",
            r"multi-?gas\s+\w+",
            r"purg(?:e|ed|ing)",
            r"venting",
            r"inert(?:ing|ed)?",
        ],
        "weight": 0.95,
    },
    "energy_isolation": {
        "label": "Energy Isolation / LOTO",
        "rule": "energy_isolation",
        "triggers": [
            r"isolat(?:ion|ed|e|ing)",
            r"lock-?out",
            r"tag-?out",
            r"\bloto\b",
            r"zero\s+energy",
            r"de-?energis\w*",
            r"de-?energiz\w*",
            r"blind(?:ed|ing|s)?(?:\s+flange)?",
            r"spade[ds]?",
            r"blank(?:ed|ing)",
            r"depressuris\w*",
            r"depressuriz\w*",
            r"blow(?:n|ing)?\s+down",
            r"drain(?:ed|ing)?",
            r"double\s+block\s+and\s+bleed",
            r"positive\s+isolation",
        ],
        "weight": 0.95,
    },
    "fire_watch": {
        "label": "Fire Watch",
        "rule": "hot_work",
        "triggers": [
            r"fire\s?watch(?:er|man|men)?",
            r"fire\s+guard",
            r"fire\s+sentry",
            r"fire\s+blanket",
            r"fire\s+extinguisher",
            r"spark\s+(?:arrest\w*|contain\w*|screen)",
            r"fire\s+suppression",
            r"standby\s+firefight\w*",
        ],
        "weight": 0.9,
    },
    "barricading": {
        "label": "Barricading / Exclusion Zone",
        "rule": "line_of_fire",
        "triggers": [
            r"barricad\w*",
            r"exclusion\s+zone",
            r"cordon(?:ed|ing)?(?:\s+off)?",
            r"safety\s+tape",
            r"warning\s+(?:sign|tape|barrier)s?",
            r"demarcat\w*",
            r"restricted\s+area",
            r"drop\s+zone",
        ],
        "weight": 0.75,
    },
    "ppe": {
        "label": "Personal Protective Equipment",
        "rule": "line_of_fire",
        "triggers": [
            r"\bppe\b",
            r"hard\s?hats?",
            r"helmets?",
            r"safety\s+glass\w*",
            r"goggles?",
            r"face\s?shield\w*",
            r"gloves?",
            r"safety\s+(?:boots|shoes)",
            r"respirator\w*",
            r"\bscba\b",
            r"breathing\s+apparatus",
            r"ear\s+(?:plug|defender|protection)\w*",
            r"flame\s+retardant",
            r"\bfrc\b",
            r"coverall\w*",
        ],
        "weight": 0.5,
    },
    "fall_protection": {
        "label": "Fall Protection",
        "rule": "working_at_height",
        "triggers": [
            r"fall\s+(?:protection|arrest|restraint)",
            r"safety\s+harness\w*",
            r"harness\w*",
            r"lanyard\w*",
            r"life-?line\w*",
            r"anchor\s+points?",
            r"safety\s+nets?",
            r"scaffold(?:ing)?\s+(?:tag|inspection|handrail)",
            r"double\s+lanyard",
            r"tie-?off",
            r"tied\s+off",
            # Passive fall prevention. These protect against a fall, so they
            # belong to Working at Height, not to area barricading.
            r"guard\s?rail\w*",
            r"hand-?rail\w*",
            r"mid-?rail\w*",
            r"toe-?board\w*",
            r"hole\s+covers?",
            r"floor\s+(?:opening\s+)?covers?",
            r"grating\w*",
            r"deck\s+plates?",
            r"man-?hole\s+covers?",
            r"hatch\s+covers?",
            r"edge\s+protection",
        ],
        "weight": 0.9,
    },
    "lifting_plan": {
        "label": "Lift Plan / Rigging Control",
        "rule": "safe_mechanical_lifting",
        "triggers": [
            r"lift(?:ing)?\s+plans?",
            r"rigging\s+(?:plan|inspection|check)",
            r"sling\s+(?:inspection|certificate|check)",
            r"load\s+(?:chart|test|certificate)",
            r"\bswl\b",
            r"safe\s+working\s+load",
            r"banks?man",
            r"signall?er",
            r"rigger",
            r"tag\s?line\w*",
            r"crane\s+(?:inspection|certificate|checklist)",
        ],
        "weight": 0.85,
    },
    "supervision": {
        "label": "Supervision / Competency",
        "rule": "work_authorisation",
        "triggers": [
            r"supervis(?:or|ion|ed|ing)",
            r"standby\s+(?:man|person|attendant|watch)",
            r"hole\s+watch",
            r"attendant",
            r"competen\w*",
            r"train(?:ed|ing)",
            r"certifi\w*",
            r"qualifi\w*",
            r"authoris(?:ed)?\s+person",
            r"spotter",
        ],
        "weight": 0.6,
    },
    "procedure_compliance": {
        "label": "Procedure Compliance",
        "rule": "bypassing_safety_controls",
        "triggers": [
            r"procedures?",
            r"\bsop\b",
            r"work\s+instructions?",
            r"operating\s+manual",
            r"checklists?",
            r"safety\s+rules?",
            r"protocols?",
        ],
        "weight": 0.55,
    },
    "safety_device": {
        "label": "Safety Device / Interlock",
        "rule": "bypassing_safety_controls",
        "triggers": [
            r"interlocks?",
            r"trips?(?:\s+system)?",
            r"\besd\b",
            r"emergency\s+shutdown",
            r"safety\s+(?:device|system|valve|switch)s?",
            r"relief\s+valves?",
            r"\bpsv\b",
            r"alarms?",
            r"limit\s+switch\w*",
            r"pressure\s+relief",
            r"machine\s+guard\w*",
            r"guards?",
            r"proximity\s+switch\w*",
            r"dead-?man\s+switch",
        ],
        "weight": 0.9,
    },
    "vehicle_safety": {
        "label": "Journey / Vehicle Control",
        "rule": "driving",
        "triggers": [
            r"seat-?belts?",
            r"journey\s+management",
            r"speed\s+limits?",
            r"defensive\s+driving",
            r"driving\s+licen[cs]e",
            r"\bivms\b",
            r"fatigue\s+management",
            r"vehicle\s+inspection",
        ],
        "weight": 0.7,
    },
}


# --------------------------------------------------------------------------
# Hazards - the energy sources that give an event fatal potential
# --------------------------------------------------------------------------

HAZARDS: dict[str, dict] = {
    "toxic_atmosphere": {
        "label": "Toxic / Oxygen-Deficient Atmosphere",
        "rule": "confined_space",
        "patterns": [
            r"\bh2s\b",
            r"hydrogen\s+sulphide",
            r"hydrogen\s+sulfide",
            r"sour\s+gas",
            r"toxic\s+(?:gas|vapou?r|atmosphere|fume)",
            r"oxygen\s+deficien\w*",
            r"asphyxiat\w*",
            r"nitrogen\s+(?:blanket|purge)",
            r"carbon\s+monoxide",
            r"noxious",
            r"fumes?",
        ],
        "sif_weight": 0.95,
    },
    "flammable_release": {
        "label": "Flammable Gas / Vapour Release",
        "rule": "hot_work",
        "patterns": [
            r"flammable",
            r"combustible",
            r"gas\s+(?:leak|release|cloud)",
            r"vapou?r\s+cloud",
            r"hydrocarbon\s+(?:leak|release|spill)",
            r"\blel\b",
            r"explosive\s+atmosphere",
            r"ignition\s+source",
            r"spark\w*",
            r"naked\s+flame",
            r"fire\s+risk",
        ],
        "sif_weight": 0.95,
    },
    "stored_energy": {
        "label": "Stored / Residual Energy",
        "rule": "energy_isolation",
        "patterns": [
            r"stored\s+energy",
            r"residual\s+(?:energy|pressure)",
            r"trapped\s+pressure",
            r"live\s+(?:electrical|circuit|line|wire|conductor)",
            r"under\s+pressure",
            r"pressuris(?:ed)?",
            r"pressuriz(?:ed)?",
            r"high\s+voltage",
            r"electrical\s+shock",
            r"arc\s+flash",
            r"spring\s+tension",
            r"hydraulic\s+pressure",
        ],
        "sif_weight": 0.9,
    },
    "uncontrolled_pressure": {
        "label": "Uncontrolled Pressure Release",
        "rule": "line_of_fire",
        "patterns": [
            r"blow-?out",
            r"well\s+control",
            r"\bkick\b",
            r"burst",
            r"rupture[ds]?",
            r"whip(?:ping|lash)",
            r"hose\s+(?:burst|failure|separat\w*)",
            r"line\s+parted",
            r"sudden\s+release",
            r"pressure\s+surge",
            r"over-?pressuris\w*",
            r"blew\s+(?:off|out)",
            r"popped\s+off",
            r"flew\s+off",
        ],
        "sif_weight": 0.95,
    },
    "suspended_load": {
        "label": "Suspended / Falling Load",
        "rule": "safe_mechanical_lifting",
        "patterns": [
            r"suspended\s+load",
            r"under\s+(?:the\s+)?load",
            r"overhead\s+load",
            r"load\s+(?:swung|swing|shifted|slipped|dropped|fell)",
            r"dropped\s+object",
            r"falling\s+object",
            r"fell\s+from\s+(?:the\s+)?(?:crane|hoist|sling|derrick|mast)",
            r"sling\s+(?:failed|broke|snapped)",
            r"rigging\s+fail\w*",
            r"crane\s+(?:tipped|collapsed)",
        ],
        "sif_weight": 0.9,
    },
    "fall_from_height": {
        "label": "Fall From Height",
        "rule": "working_at_height",
        "patterns": [
            r"fall\s+(?:to|from)\s+\w+",
            r"fell\s+(?:from|off|through)",
            r"fell\s+a\s+distance",
            r"working\s+at\s+heights?",
            r"elevated\s+\w+",
            r"walkway",
            r"catwalk",
            r"gantry",
            r"floor\s+opening",
            r"open\s+grating",
            r"derrick",
            r"\bmast\b",
            r"monkey\s?board",
            r"scaffold\w*",
            r"ladder",
            r"open\s+(?:hole|hatch|grating)",
            r"unprotected\s+edge",
            r"platform\s+edge",
            r"\bmezzanine\b",
        ],
        "sif_weight": 0.9,
    },
    "line_of_fire": {
        "label": "Line of Fire / Struck-By",
        "rule": "line_of_fire",
        "patterns": [
            r"line\s+of\s+fire",
            r"struck\s+by",
            r"hit\s+by",
            r"caught\s+(?:in|between)",
            r"pinch\s+points?",
            r"crush(?:ed|ing)?",
            r"pinned",
            r"trapped\s+between",
            r"rotating\s+(?:equipment|machinery|shaft)",
            r"moving\s+(?:parts|machinery|equipment)",
            r"\btongs?\b",
            r"spinning\s+chain",
            r"drill\s+(?:floor|pipe|string)",
            r"amputat\w*",
            r"degloved",
            r"severed",
        ],
        "sif_weight": 0.85,
    },
    "vehicle_incident": {
        "label": "Vehicle / Mobile Equipment",
        "rule": "driving",
        "patterns": [
            r"vehicle\s+(?:collision|accident|rollover|roll-?over)",
            r"road\s+traffic",
            r"overturn\w*",
            r"reversing",
            r"forklift",
            r"crane\s+truck",
            r"speeding",
            r"lost\s+control\s+of\s+(?:the\s+)?vehicle",
            r"skidd\w*",
            r"run\s+over",
            r"struck\s+by\s+(?:a\s+)?(?:vehicle|truck|trailer)",
        ],
        "sif_weight": 0.85,
    },
    "chemical_exposure": {
        "label": "Hazardous Chemical Exposure",
        "rule": "line_of_fire",
        "patterns": [
            r"chemical\s+(?:burn|exposure|splash|spill|contact)",
            r"\bacid\b",
            r"caustic",
            r"corrosive",
            r"solvent",
            r"drilling\s+(?:mud|fluid)",
            r"splash\w*",
            r"toxic\s+(?:liquid|substance)",
            r"hazardous\s+(?:substance|material|chemical)",
        ],
        "sif_weight": 0.75,
    },
    "thermal": {
        "label": "Thermal / Burn Exposure",
        "rule": "hot_work",
        "patterns": [
            r"burn(?:s|ed|ing)?\b",
            r"scald\w*",
            r"steam\s+(?:leak|release|burn)",
            r"hot\s+(?:surface|oil|water)",
            r"flash\s+fire",
            r"explosion",
            r"fire\s+(?:broke|started|occurred)",
            r"molten",
            r"ignited",
        ],
        "sif_weight": 0.9,
    },
    "excavation": {
        "label": "Excavation / Ground Collapse",
        "rule": "confined_space",
        "patterns": [
            r"excavation",
            r"trench\w*",
            r"shoring",
            r"cave-?in",
            r"collapse[ds]?",
            r"buried",
            r"engulf\w*",
            r"soil\s+(?:collapse|slide)",
        ],
        "sif_weight": 0.9,
    },
}


# --------------------------------------------------------------------------
# Which hazard mentions denote an ACTUAL uncontrolled energy event, as opposed
# to equipment or a location that merely implies potential.
#
# The distinction matters for precursor reporting. "Gas leak from the flange" is
# a precursor on its own - energy escaped. "Scaffold handrail was installed and
# inspected" mentions a fall hazard context, but nothing escaped and every
# control held; calling that a precursor is a false alarm.
#
# So a hazard listed here counts as a precursor by itself. Any other hazard
# mention only becomes a precursor when a barrier also failed.
# --------------------------------------------------------------------------

HAZARD_EVENT_PATTERNS: dict[str, list[str]] = {
    "toxic_atmosphere": [
        r"toxic\s+(?:gas|vapou?r|atmosphere|fume)", r"oxygen\s+deficien\w*",
        r"asphyxiat\w*", r"noxious", r"gas\s+(?:leak|release)",
    ],
    "flammable_release": [
        r"gas\s+(?:leak|release|cloud)", r"vapou?r\s+cloud",
        r"hydrocarbon\s+(?:leak|release|spill)", r"explosive\s+atmosphere",
    ],
    "stored_energy": [
        r"electrical\s+shock", r"arc\s+flash",
        r"still\s+(?:pressuris|pressuriz|energis|energiz)\w*",
    ],
    "uncontrolled_pressure": [
        r"blow-?out", r"burst", r"rupture[ds]?", r"whip(?:ping|lash)",
        r"hose\s+(?:burst|failure|separat\w*)", r"line\s+parted",
        r"sudden\s+release", r"blew\s+(?:off|out)", r"popped\s+off", r"flew\s+off",
    ],
    "suspended_load": [
        r"load\s+(?:swung|swing|shifted|slipped|dropped|fell)", r"dropped\s+object",
        r"falling\s+object", r"sling\s+(?:failed|broke|snapped)",
        r"rigging\s+fail\w*", r"crane\s+(?:tipped|collapsed)",
    ],
    "fall_from_height": [
        r"fell\s+(?:from|off|through)", r"fell\s+a\s+distance",
        r"fall\s+(?:to|from)\s+\w+", r"unprotected\s+edge",
    ],
    "line_of_fire": [
        r"struck\s+by", r"hit\s+by", r"caught\s+(?:in|between)",
        r"crush(?:ed|ing)?", r"pinned", r"trapped\s+between", r"severed",
    ],
    "vehicle_incident": [
        r"vehicle\s+(?:collision|accident|rollover|roll-?over)", r"overturn\w*",
        r"lost\s+control\s+of\s+(?:the\s+)?vehicle", r"run\s+over",
        r"struck\s+by\s+(?:a\s+)?(?:vehicle|truck|trailer)",
    ],
    "chemical_exposure": [
        r"chemical\s+(?:burn|exposure|splash|spill|contact)", r"splash\w*",
    ],
    "thermal": [
        r"flash\s+fire", r"explosion", r"fire\s+(?:broke|started|occurred)",
        r"ignited", r"steam\s+(?:leak|release|burn)", r"scald\w*",
    ],
    "excavation": [
        r"cave-?in", r"collapse[ds]?", r"buried", r"engulf\w*",
    ],
}


# --------------------------------------------------------------------------
# Work activity taxonomy
# --------------------------------------------------------------------------

ACTIVITIES: dict[str, dict] = {
    "confined_space_entry": {
        "label": "Confined Space Entry",
        "patterns": [
            r"confined\s+space",
            r"enter(?:ed|ing)?\s+(?:the\s+)?(?:vessel|tank|pit|sump|silo|drum)",
            r"vessel\s+entry",
            r"tank\s+(?:entry|cleaning)",
            r"man-?way",
            r"internal\s+inspection",
        ],
    },
    "hot_work": {
        "label": "Hot Work / Welding",
        "patterns": [
            r"weld(?:ing|er|ed)?",
            r"cutting\s+(?:torch|operation)",
            r"gas\s+cutting",
            r"grind(?:ing|er)",
            r"burning",
            r"brazing",
            r"soldering",
            r"hot\s+work",
            r"arc\s+welding",
            r"flame\s+cutting",
        ],
    },
    "drilling": {
        "label": "Drilling Operations",
        "patterns": [
            r"drill(?:ing)?\s+(?:rig|floor|crew|operation)",
            r"drill\s+(?:pipe|string|collar)",
            r"tripping\s+(?:in|out)",
            r"making\s+up\s+(?:a\s+)?(?:connection|joint)",
            r"\btongs?\b",
            r"rotary\s+table",
            r"mud\s+pump",
            r"\bbop\b",
            r"blow-?out\s+preventer",
            r"casing",
            r"cementing",
            r"derrick",
            r"draw-?works",
        ],
    },
    "workover": {
        "label": "Workover / Well Intervention",
        "patterns": [
            r"work-?over",
            r"well\s+intervention",
            r"wire-?line",
            r"coiled\s+tubing",
            r"snubbing",
            r"well\s+servicing",
            r"pulling\s+(?:rods|tubing)",
            r"swabbing",
            r"perforat\w*",
            r"stimulation",
            r"frac(?:turing|k)\w*",
            r"acidiz\w*",
        ],
    },
    "maintenance": {
        "label": "Maintenance / Repair",
        "patterns": [
            r"maintenance",
            r"repair(?:ing|ed|s)?",
            r"servicing",
            r"overhaul",
            r"replac(?:ing|ed|ement)",
            r"dismantl\w*",
            r"disassembl\w*",
            r"troubleshoot\w*",
            r"break(?:ing)?\s+containment",
            r"open(?:ing|ed)\s+(?:up\s+)?(?:the\s+)?(?:line|flange|valve)",
        ],
    },
    "lifting": {
        "label": "Lifting / Rigging",
        "patterns": [
            r"lift(?:ing)?\s+operation",
            r"crane",
            r"hoist(?:ing)?",
            r"rigging",
            r"sling",
            r"shackle",
            r"winch",
            r"forklift",
            r"load\s+(?:handling|movement)",
            r"\bboom\b",
        ],
    },
    "working_at_height": {
        "label": "Working at Height",
        "patterns": [
            r"working\s+at\s+heights?",
            r"scaffold\w*",
            r"ladder",
            r"elevated\s+platform",
            r"\bmewp\b",
            r"cherry\s+picker",
            r"man-?lift",
            r"climb(?:ing|ed)",
            r"monkey\s?board",
            r"roof\s+work",
            r"platform\s+work",
        ],
    },
    "electrical_work": {
        "label": "Electrical Work",
        "patterns": [
            r"electrical\s+(?:work|maintenance|panel|installation)",
            r"switch-?gear",
            r"\bmcc\b",
            r"transformer",
            r"cable\s+(?:pulling|termination|jointing)",
            r"circuit\s+breaker",
            r"busbar",
            r"wiring",
            r"junction\s+box",
        ],
    },
    "excavation": {
        "label": "Excavation / Civil Work",
        "patterns": [
            r"excavation",
            r"trench(?:ing)?",
            r"digging",
            r"earth-?work",
            r"civil\s+work",
            r"pipeline\s+(?:laying|construction)",
            r"boring",
        ],
    },
    "transport": {
        "label": "Transport / Driving",
        "patterns": [
            r"driv(?:ing|er|e)\b",
            r"vehicle\s+(?:movement|operation)",
            r"transport\w*",
            r"journey",
            r"convoy",
            r"reversing",
            r"haulage",
        ],
    },
    "production_ops": {
        "label": "Production Operations",
        "patterns": [
            r"production\s+(?:operation|facility|platform)",
            r"separator",
            r"flow-?line",
            r"well-?head",
            r"christmas\s+tree",
            r"manifold",
            r"gas\s+(?:plant|compression)",
            r"pigging",
            r"sampling",
            r"gauging",
            r"tank\s+farm",
            r"pump\s+station",
        ],
    },
    "inspection": {
        "label": "Inspection / Testing",
        "patterns": [
            r"inspect(?:ion|ing|ed)",
            r"\bndt\b",
            r"radiograph\w*",
            r"ultrasonic",
            r"pressure\s+test\w*",
            r"hydro-?test\w*",
            r"survey(?:ing)?",
            r"calibrat\w*",
        ],
    },
}


# --------------------------------------------------------------------------
# Outcome severity language - signals real (not just potential) consequence
# --------------------------------------------------------------------------

SEVERITY_CUES: dict[str, float] = {
    r"fatal(?:ity|ities)?": 1.0,
    r"death|died|deceased|killed": 1.0,
    r"amputat\w*": 0.85,
    r"sever(?:ed|ing)\b": 0.85,
    r"degloved": 0.8,
    r"crush(?:ed|ing)": 0.8,
    r"fractur\w*": 0.6,
    r"unconscious": 0.85,
    r"asphyxiat\w*": 0.95,
    r"electrocut\w*": 0.95,
    r"third[- ]degree\s+burn": 0.9,
    r"critical(?:ly)?\s+(?:injur|ill)\w*": 0.9,
    r"life-?threatening": 0.95,
    r"hospitali[sz]\w*": 0.5,
    r"internal\s+(?:injur|bleed)\w*": 0.75,
    r"spinal|paraly\w*": 0.9,
    r"traumatic": 0.7,
}


# --------------------------------------------------------------------------
# Phrase normalisation - collapse surface variants to one canonical concept.
# The spec requires "fire watcher absent" / "no fire watch" / "firewatch
# missing" to all become "Fire Watch Missing".
# --------------------------------------------------------------------------

_FAILURE_SUFFIX: dict[str, str] = {
    "permit_to_work": "Missing / Invalid",
    "risk_assessment": "Not Performed",
    "gas_testing": "Not Performed",
    "energy_isolation": "Not Verified",
    "fire_watch": "Missing",
    "barricading": "Missing",
    "ppe": "Not Used",
    "fall_protection": "Not Used",
    "lifting_plan": "Missing / Inadequate",
    "supervision": "Absent / Not Competent",
    "procedure_compliance": "Not Followed",
    "safety_device": "Bypassed / Defeated",
    "vehicle_safety": "Not Followed",
}


def canonical_barrier_failure(barrier_key: str) -> str:
    """Canonical human-readable name for a failed barrier concept."""
    suffix = _FAILURE_SUFFIX.get(barrier_key, "Failed")
    return f"{BARRIERS[barrier_key]['label']} {suffix}"


# Report types used by OIL's HSSE reporting workflow
REPORT_TYPES = ["Unsafe Act", "Unsafe Condition", "Near Miss", "Incident"]

# Risk bands
RISK_LEVELS = ["Low", "Medium", "High", "Critical"]


# --------------------------------------------------------------------------
# Implied hazard and exposure
#
# A narrative often names the activity but leaves the energy source implicit.
# "Entered the confined space before gas testing" never says "toxic atmosphere",
# yet that is precisely the fatal-potential exposure an HSE reviewer infers.
# These maps make that inference explicit and auditable.
# --------------------------------------------------------------------------

ACTIVITY_IMPLIED_HAZARDS: dict[str, list[str]] = {
    "confined_space_entry": ["toxic_atmosphere"],
    "hot_work": ["flammable_release", "thermal"],
    "drilling": ["line_of_fire", "uncontrolled_pressure"],
    "workover": ["uncontrolled_pressure", "line_of_fire"],
    "maintenance": ["stored_energy"],
    "lifting": ["suspended_load"],
    "working_at_height": ["fall_from_height"],
    "electrical_work": ["stored_energy"],
    "excavation": ["excavation"],
    "transport": ["vehicle_incident"],
    "production_ops": ["stored_energy"],
    "inspection": [],
}

# How the worker is exposed, phrased the way an HSE professional would write it.
EXPOSURE_TEMPLATES: dict[str, str] = {
    "confined_space_entry": "Person inside confined space with restricted egress",
    "hot_work": "Ignition source in potentially flammable atmosphere",
    "drilling": "Person on drill floor near rotating and pressurised equipment",
    "workover": "Person near live well with pressure-containment reliance",
    "maintenance": "Person in contact with equipment holding residual energy",
    "lifting": "Person within fall or swing zone of a suspended load",
    "working_at_height": "Person exposed to an unprotected fall to a lower level",
    "electrical_work": "Person in contact with, or close to, live conductors",
    "excavation": "Person inside excavation exposed to collapse or engulfment",
    "transport": "Person in or near a moving vehicle",
    "production_ops": "Person near pressurised hydrocarbon-containing equipment",
    "inspection": "Person adjacent to equipment under test",
}
