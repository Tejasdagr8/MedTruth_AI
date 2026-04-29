from src.retrieval.intent_filter import matches_intent


def test_matches_intent_keeps_aligned_aspirin_mi_mortality_doc():
    query = "Does aspirin reduce mortality in acute myocardial infarction?"
    doc = {
        "metadata": {"title": "Aspirin and mortality in acute myocardial infarction"},
        "text": "Trial shows improved survival and reduced mortality with aspirin in MI patients.",
    }
    assert matches_intent(doc, query) is True


def test_matches_intent_rejects_partial_alignment_doc():
    query = "Does aspirin reduce mortality in acute myocardial infarction?"
    doc = {
        "metadata": {"title": "Ticagrelor in acute ischemic stroke"},
        "text": "Study evaluates stroke outcomes and platelet inhibition in ischemic stroke cohorts.",
    }
    assert matches_intent(doc, query) is False
