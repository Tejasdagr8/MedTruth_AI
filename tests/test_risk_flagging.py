import pytest
from src.features.risk_flagging import flag_query, get_overall_risk_level, RiskLevel


def test_dosage_query_flagged():
    flags = flag_query("What is the recommended dose of metformin for type 2 diabetes?")
    categories = [f.category for f in flags]
    assert any("Dosage" in c or "Prescription" in c for c in categories)


def test_pediatric_query_flagged():
    flags = flag_query("Can ibuprofen be given to children under 2 years?")
    categories = [f.category for f in flags]
    assert any("Pediatric" in c for c in categories)


def test_pregnancy_query_flagged():
    flags = flag_query("Is methotrexate safe during pregnancy?")
    categories = [f.category for f in flags]
    assert any("Pregnancy" in c for c in categories)


def test_high_risk_is_overall_high():
    flags = flag_query("Dosage of warfarin in pediatric patients")
    level = get_overall_risk_level(flags)
    assert level == RiskLevel.HIGH


def test_benign_query_has_no_flags():
    flags = flag_query("What is the definition of hypertension?")
    assert len(flags) == 0


def test_emergency_query_flagged():
    flags = flag_query("What to do during cardiac arrest and CPR?")
    categories = [f.category for f in flags]
    assert any("Acute Care" in c for c in categories)


def test_mental_health_query_does_not_trigger_emergency_flag():
    flags = flag_query(
        "Is CBT effective for depression?",
        "Psychotherapy can reduce depressive symptoms and improve function.",
    )
    categories = [f.category for f in flags]
    assert not any("Emergency" in c for c in categories)
    assert len(flags) == 0


def test_pediatric_not_flagged_when_only_answer_mentions_children():
    flags = flag_query(
        "Is CBT effective for major depressive disorder?",
        "Several studies include children and adolescents with depressive symptoms.",
    )
    categories = [f.category for f in flags]
    assert not any("Pediatric" in c for c in categories)
