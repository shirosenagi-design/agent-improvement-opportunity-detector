from core.measure import measure_pair

def test_context_hits_can_differ():
    m=measure_pair('What should I build first?','I prefer prototypes and hate long checklists.','Consider several options. It depends.','Start with one of those prototypes, then test it.')
    assert m['personalized_mode']['personal_context_term_hits'] >= 1
    assert m['population_mode']['generic_phrase_hits'] >= 1

def test_overlap_is_bounded():
    m=measure_pair('x','','alpha beta gamma','alpha beta delta')
    assert 0 <= m['response_lexical_overlap'] <= 1
