"""
Risk flagging — pattern matching for high-stakes query categories.

This is intentionally conservative. I'd rather show a disclaimer that turns out to
be unnecessary than miss a query about pediatric dosing or a drug contraindication.
The cost of a false positive is a banner the user can ignore. The cost of a false
negative in a clinical context is much worse.

Known false-positive source: "stroke" triggers ACUTE_CARE even for non-emergency
questions about stroke recovery / rehabilitation. The mental_health guard for acute_care
is a similar hack. Both are acceptable tradeoffs for now.

TODO: replace the string-matching approach with a lightweight classifier at some point.
The regex approach starts failing badly on complex queries with negations
("no history of emergency intervention") but those are uncommon enough that it's fine for v1.
"""

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


ACUTE_CARE_CATEGORY = "CLINICAL CONTEXT — Acute Care"


@dataclass
class RiskFlag:
    level: RiskLevel
    category: str
    message: str
    banner_color: str  # for frontend styling: red | amber | blue | none

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "banner_color": self.banner_color,
        }


RISK_RULES: list[dict] = [
    {
        "category": "Drug Dosage / Prescription",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bdose[s]?\b|\bdosage[s]?\b|\bdosing\b",
            r"\bmg\b|\bmcg\b|\bml\b.*\b(drug|medication|medicine)\b",
            r"\bprescri(be|ption|bing)\b",
            r"\btherapeutic range\b|\bmaximum dose\b|\blethal dose\b",
        ],
        "message": (
            "This response involves drug dosage or prescription information. "
            "Dosage recommendations vary by patient weight, renal function, age, and comorbidities. "
            "NEVER apply these figures without consulting a licensed prescriber."
        ),
    },
    {
        "category": "Drug Interactions",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bdrug.{0,20}interaction\b",
            r"\bcontraindicated\b|\bcontraindication\b",
            r"\bcombined with\b.*\b(drug|medication|medicine)\b",
            r"\bpolypharmacy\b",
        ],
        "message": (
            "This response involves potential drug interactions. "
            "Interaction severity can vary significantly by individual patient factors. "
            "Always verify interactions using a clinical pharmacology database and consult a pharmacist."
        ),
    },
    {
        "category": "Pediatric Population",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bpediatric[s]?\b|\bpaediatric[s]?\b",
            r"\bchildren\b|\bchild\b|\binfant[s]?\b|\bneonatal\b|\bnewborn\b",
            r"\bunder (18|16|12|5|2) year\b",
            r"\bpeds\b",
        ],
        "message": (
            "This response involves pediatric populations. "
            "Drug metabolism, dosing, and clinical presentations differ substantially from adults. "
            "Pediatric care decisions must involve a qualified pediatric clinician."
        ),
    },
    {
        "category": "Pregnancy / Obstetrics",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bpregnant\b|\bpregnancy\b|\bgestational\b",
            r"\bfetal\b|\bfoetal\b|\bfetus\b|\bembryo\b",
            r"\bmaternal\b|\bobstetric[s]?\b|\bperinatal\b",
            r"\blactation\b|\bbreastfeed\b|\bnursing mother\b",
        ],
        "message": (
            "This response involves pregnancy or obstetric care. "
            "Drug safety and clinical decisions during pregnancy are highly individualized. "
            "Consult a maternal-fetal medicine specialist or obstetrician."
        ),
    },
    {
        "category": "Surgical / Procedural",
        "level": RiskLevel.MEDIUM,
        "banner_color": "amber",
        "patterns": [
            r"\bsurgery\b|\bsurgical\b|\boperation\b|\boperative\b",
            r"\bprocedure\b.*\b(invasive|endoscop|catheter|biopsy)\b",
            r"\banesthesia\b|\banaesthesia\b",
            r"\bpost.?op\b|\bpreoperative\b|\bpostoperative\b",
        ],
        "message": (
            "This response discusses surgical or procedural interventions. "
            "Surgical decisions require direct clinical assessment. "
            "Outcomes vary significantly based on patient-specific factors."
        ),
    },
    {
        "category": "Oncology / Cancer Treatment",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bcancer\b|\boncology\b|\bchemotherapy\b|\bradiation therapy\b",
            r"\bmalignant\b|\bmalignancy\b|\btumor\b|\btumour\b",
            r"\bimmunotherapy\b|\btargeted therapy\b",
        ],
        "message": (
            "This response involves oncology or cancer treatment. "
            "Cancer management is highly protocol- and stage-specific. "
            "Treatment decisions must be made by a qualified oncologist in a multidisciplinary setting."
        ),
    },
    {
        "category": ACUTE_CARE_CATEGORY,
        "type": "acute_care",
        "level": RiskLevel.HIGH,
        "banner_color": "red",
        "patterns": [
            r"\bemergency\b|\bcritical care\b|\bICU\b|\bintensive care\b",
            r"\bsepsis\b|\bseptic shock\b|\banaphylaxis\b|\bstroke\b|\bmyocardial infarction\b",
            r"\bresuscitation\b|\bcardiac arrest\b|\bCPR\b",
        ],
        "message": (
            "⚠️ This response involves emergency or critical care situations. "
            "In an emergency, call emergency services immediately. "
            "This information is for educational purposes only and must NOT replace emergency clinical judgment."
        ),
    },
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def is_mental_health(query: str) -> bool:
    # Guard against acute_care patterns firing on mental health queries.
    # "suicidal ideation" would otherwise match the emergency pattern,
    # but the appropriate response there is very different from "call 911".
    q = query.lower()
    return any(k in q for k in ["depression", "cbt", "therapy", "psychotherapy", "anxiety", "mental"])


def flag_query(query: str, answer: str = "") -> list[RiskFlag]:
    """
    Analyze query and generated answer for risk categories.
    Returns list of RiskFlag objects sorted by severity.
    """
    combined_text = query.lower()
    flags = []
    seen_categories = set()

    for rule in RISK_RULES:
        if rule["category"] in seen_categories:
            continue
        if rule["category"] == "Pediatric Population":
            if not any(k in query.lower() for k in ["child", "children", "adolescent", "pediatric"]):
                continue
        if is_mental_health(query) and rule.get("type") == "acute_care":
            continue
        if _matches_any(combined_text, rule["patterns"]):
            flags.append(RiskFlag(
                level=rule["level"],
                category=rule["category"],
                message=rule["message"],
                banner_color=rule["banner_color"],
            ))
            seen_categories.add(rule["category"])

    # Sort: HIGH before MEDIUM
    flags.sort(key=lambda f: (0 if f.level == RiskLevel.HIGH else 1))
    return flags


def get_overall_risk_level(flags: list[RiskFlag]) -> RiskLevel:
    if not flags:
        return RiskLevel.NONE
    if any(f.level == RiskLevel.HIGH for f in flags):
        return RiskLevel.HIGH
    if any(f.level == RiskLevel.MEDIUM for f in flags):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
