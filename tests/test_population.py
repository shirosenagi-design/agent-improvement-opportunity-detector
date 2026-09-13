from core.population import simulate_population

def test_population_is_deterministic():
    assert simulate_population('balanced',1000,42).model_dump() == simulate_population('balanced',1000,42).model_dump()

def test_population_is_bounded():
    p=simulate_population('cautious_consensus',1000,7)
    for s in p.dimensions.values(): assert 0 <= s.p10 <= s.mean <= s.p90 <= 1

def test_population_is_explicitly_synthetic():
    assert 'Synthetic' in simulate_population('balanced',100,1).note
