from core.personalization import normalize_mbti
from core.schemas import ProvisionalUserModel, ResearchQuestion

def test_mbti_is_only_normalized_not_fixed_to_counterpart():
    assert normalize_mbti('infj') == 'INFJ'

def test_provisional_user_model_survives_v6():
    model = ProvisionalUserModel(
        summary='Needs decisive but reasoned collaboration.',
        explicit_signals=['dislikes long option lists'],
        working_hypotheses=['may benefit from one strong recommendation'],
        interaction_needs=['preserve agency'],
        likely_friction_points=['generic checklists'],
        personalization_policy=['foreground one recommendation and reasoning'],
        do_not_assume=['MBTI describes the whole person'],
        confidence='MEDIUM',
    )
    assert model.confidence == 'MEDIUM'

def test_research_question_stops_before_conclusion():
    q = ResearchQuestion(
        title='Decision framing',
        observed_difference='B reframed the choice around minimum thresholds while A used a broad checklist.',
        evidence_from_population=['Compare both offers.'],
        evidence_from_personalized=['What minimum stability do you actually need?'],
        question_to_test='Across users who explicitly report option overload, does threshold framing improve decision usefulness without removing important baseline risk checks?',
    )
    assert q.question_to_test.endswith('?')
