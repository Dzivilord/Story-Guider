from dataclasses import dataclass
MODEL_VERSION='content_model_d_v1'
RATING_STRENGTH={1:-1.0,2:-0.5,3:0.0,4:0.5,5:1.0}
@dataclass(frozen=True)
class RecommendationConfig:
    candidate_k:int=100; final_k:int=20; negative_weight:float=.35; semantic_weight:float=.45; genre_weight:float=.15; author_weight:float=.1; quality_weight:float=.08
