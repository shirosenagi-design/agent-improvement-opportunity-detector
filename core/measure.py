import re
GENERIC=('it may be helpful','consider','you could','it depends','talk to','reach out','take some time','there are several','one option')
CAUTION=('risk','safety','careful','caution','harm','professional','qualified','emergency','crisis')
DIRECT=('start with','first,','i would','do this','choose','build','write','test','ask')

def _count(t, ps):
    t=t.lower(); return sum(t.count(p) for p in ps)

def _overlap(a,b):
    tok=lambda s:set(re.findall(r'[A-Za-z0-9ぁ-んァ-ヶ一-龠]{2,}', s.lower()))
    aa,bb=tok(a),tok(b)
    return round(len(aa & bb)/len(aa | bb),3) if aa and bb else 0.0

def measure_pair(prompt,self_intro,pop,personal):
    terms=set(re.findall(r'[A-Za-z0-9ぁ-んァ-ヶ一-龠]{3,}', self_intro.lower()))
    def one(t):
        lo=t.lower(); hits=sum(term in lo for term in terms) if self_intro.strip() else 0
        return {'generic_phrase_hits':_count(t,GENERIC),'caution_phrase_hits':_count(t,CAUTION),'directive_phrase_hits':_count(t,DIRECT),'self_intro_term_hits':hits,'personal_context_term_hits':hits}
    return {'population_mode':one(pop),'personalized_mode':one(personal),'response_lexical_overlap':_overlap(pop,personal),'measurement_scope':'Supporting surface measurements only. No brevity, length, readability, sentence-count, or generic cognitive-load metric is treated as a quality signal. Semantic opportunity claims require exact quoted evidence.'}
