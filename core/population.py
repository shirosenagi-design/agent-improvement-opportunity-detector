import math, random
from .schemas import DistributionStat, PopulationProfile, PopulationWeights

PRESET_MEANS = {
    'balanced': PopulationWeights(),
    'cautious_consensus': PopulationWeights(caution=.84, consensus=.82, directness=.42, warmth=.52, novelty=.28, context_sensitivity=.34),
    'creative_exploratory': PopulationWeights(caution=.54, consensus=.42, directness=.61, warmth=.53, novelty=.82, context_sensitivity=.47),
    'warm_relational': PopulationWeights(caution=.62, consensus=.50, directness=.55, warmth=.86, novelty=.51, context_sensitivity=.81),
}

def _clip(v): return max(0.0, min(1.0, v))
def _pct(v,q):
    pos=(len(v)-1)*q; lo=math.floor(pos); hi=math.ceil(pos)
    return v[lo] if lo==hi else v[lo]*(hi-pos)+v[hi]*(pos-lo)

def simulate_population(preset:str,size:int,seed:int,override:PopulationWeights|None=None)->PopulationProfile:
    means=override or PRESET_MEANS[preset]; rng=random.Random(seed); raw={k:[] for k in means.model_dump()}
    for _ in range(size):
        for k,m in means.model_dump().items(): raw[k].append(_clip(rng.gauss(float(m),.17)))
    dims={}
    for k,v in raw.items():
        v.sort(); dims[k]=DistributionStat(mean=round(sum(v)/len(v),3),p10=round(_pct(v,.1),3),p90=round(_pct(v,.9),3))
    return PopulationProfile(size=size,seed=seed,preset=preset,dimensions=dims,note='Synthetic simulated population; not real users, votes, feedback records, or training examples.')

def profile_as_prompt(p):
    return ', '.join(f'{k}={v.mean:.3f}' for k,v in p.dimensions.items())
