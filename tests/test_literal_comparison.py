from app.agent.comparison import common_literal_terms, overlap_note
from test_extractive_safety import passage


def test_literal_overlap_is_grouped_by_ingredient_not_number_of_passages():
    first = passage("Severe hypersensitivity and bleeding.", drug="warfarin")
    same = passage("Bleeding only", drug="warfarin", pid="p2")
    assert common_literal_terms([first, same]) == []
    second = passage("Active bleeding; severe hypersensitivity.", drug="apixaban", pid="p3")
    result = common_literal_terms([first, same, second])
    assert "bleeding" in result and "hypersensitivity" in result
    assert "clinical equivalence" in overlap_note(result)


def test_overlap_does_not_infer_equivalent_categories_or_clinical_uniqueness():
    first = passage("Hemorrhagic tendencies.", drug="warfarin")
    second = passage("Active pathological bleeding.", drug="apixaban", pid="p2")
    assert common_literal_terms([first, second]) == []
