from src.retrieval.pubmed_client import expand_query


def test_expand_query_for_cbt():
    query = "Is cognitive behavioral therapy effective for major depressive disorder?"
    expanded = expand_query(query)
    assert "cognitive behavioral therapy OR CBT" in expanded
    assert "depression" in expanded
    assert "major depressive disorder" in expanded
    assert 'adult OR "general population"' in expanded


def test_expand_query_passthrough_for_non_cbt():
    query = "Does aspirin reduce mortality in myocardial infarction?"
    assert expand_query(query) == query
