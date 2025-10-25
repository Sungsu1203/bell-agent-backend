from utils.sanitize import sanitize_state

def test_sanitize_in_place():
    st = {"research_round":"2","iteration_count":"3","new_url_count":None}
    out = sanitize_state(st)  # in-place
    assert out["research_round"] == 2
    assert out["iteration_count"] == 3
    assert out["new_url_count"] is None
