from core.personalization import normalize_mbti

def test_mbti_seed_is_normalized_without_fixed_counterpart_mapping():
    assert normalize_mbti('infj') == 'INFJ'
