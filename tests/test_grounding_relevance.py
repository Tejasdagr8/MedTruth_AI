from src.retrieval.relevance_filter import is_relevant
from src.retrieval.domain_classifier import detect_domain
from src.rag.grounding import filter_grounded_sentences


def test_is_relevant_filters_off_topic_documents():
    query = "Does aspirin reduce mortality in acute myocardial infarction?"
    relevant_doc = {
        "metadata": {"title": "Aspirin mortality benefit in myocardial infarction"},
        "text": "Randomized trial in acute myocardial infarction reports lower mortality with aspirin.",
    }
    noisy_doc = {
        "metadata": {"title": "Kawasaki disease management update"},
        "text": "Review of pediatric vasculitis and treatment response.",
    }
    assert is_relevant(relevant_doc, query) is True
    assert is_relevant(noisy_doc, query) is False


def test_filter_grounded_sentences_keeps_supported_claims():
    docs = [
        {
            "text": (
                "ISIS-2 trial showed aspirin reduced vascular mortality in acute myocardial "
                "infarction patients over five weeks."
            )
        }
    ]
    answer = (
        "Aspirin reduced vascular mortality in acute myocardial infarction patients. "
        "This has no relation to Kawasaki disease in children."
    )
    filtered = filter_grounded_sentences(answer, docs, min_similarity=0.2)
    assert "Aspirin reduced vascular mortality" in filtered
    assert "Kawasaki disease" not in filtered


def test_detect_domain_for_mental_health_query():
    query = "Is CBT effective for depression and anxiety?"
    assert detect_domain(query) == "mental_health"
