from agent.heuristics import HEURISTICS

def test_ten_unique_heuristics():
    assert len(HEURISTICS) == 10
    assert [h["id"] for h in HEURISTICS] == list(range(1, 11))
    assert len({h["name"] for h in HEURISTICS}) == 10
