from pathlib import Path
from core.measure import measure_pair
from core.schemas import OpportunityPacket, ResearchQuestion
ROOT=Path(__file__).resolve().parents[1]

def test_measurement_does_not_emit_length_quality_signals():
    m=measure_pair('q','short bio','answer one','answer two')
    for side in ('population_mode','personalized_mode'):
        assert 'characters' not in m[side]
        assert 'sentences' not in m[side]
    assert 'brevity' in m['measurement_scope'].lower()

def test_orchestrator_is_asymmetric_research_instrument():
    t=(ROOT/'core'/'trial.py').read_text(encoding='utf-8')
    assert 'intentionally ASYMMETRIC' in t and 'research instrument' in t and "which answer wins" in t

def test_mbti_is_bootstrap_not_target():
    t=(ROOT/'core'/'trial.py').read_text(encoding='utf-8')
    assert 'MBTI is only bootstrap context' in t

def test_research_boundary_is_non_prescriptive():
    t=(ROOT/'core'/'trial.py').read_text(encoding='utf-8')
    assert 'Do NOT tell the developer what to implement' in t
    assert 'PROJECT 04 supplies evidence and testable questions, not conclusions' in t

def test_packet_has_questions_not_implementation_decisions():
    assert 'research_questions' in OpportunityPacket.model_fields
    assert 'opportunities' not in OpportunityPacket.model_fields
    assert {'title','observed_difference','evidence_from_population','evidence_from_personalized','question_to_test'} == set(ResearchQuestion.model_fields)

def test_ui_prioritizes_questions_and_collapses_trace():
    h=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    assert 'RAW RESPONSE PAIR · NOT NORMALIZED' in h
    assert 'OBSERVED DIFFERENCES → QUESTIONS TO TEST' in h
    assert '<details><summary><b>Actual Agent Trace</b>' in h
    assert '<details open><summary><b>Actual Agent Trace</b>' not in h
    js=(ROOT/'static'/'app.js').read_text(encoding='utf-8')
    assert 'Developer hypothesis' not in js
    assert 'Human decision' not in js
