from __future__ import annotations
import json
import numpy as np
from dataclasses import dataclass
from ..models import Book, Interaction
from ..semantic import SemanticBookRetriever
from .config import RecommendationConfig, MODEL_VERSION
from .profile import UserContentProfile, aggregate_interactions, build_profile

@dataclass
class Recommendation:
    work_id: int
    score: float
    components: dict
    matched_interests: list[int]

class BookFeatureProvider:
    def __init__(self, retriever: SemanticBookRetriever):
        self.retriever=retriever
        self.vectors={int(work_id):np.asarray(retriever.index.reconstruct(pos),dtype='float32') for pos,work_id in enumerate(retriever.mapping)}
    def vector(self, work_id): return self.vectors.get(work_id)

class ContentRecommendationService:
    def __init__(self, db, semantic_retriever=None, config=None):
        self.db=db; self.config=config or RecommendationConfig(); self.semantic=semantic_retriever or SemanticBookRetriever(); self.features=BookFeatureProvider(self.semantic)
    def build_profile(self,user_id):
        rows=self.db.query(Interaction).filter(Interaction.user_id==user_id).all(); ids=[r.work_id for r in rows]
        books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}
        return build_profile(user_id,aggregate_interactions(rows),books,self.features.vectors,self.config.interest_similarity_threshold)
    def recommend(self,user_id:str,top_k:int|None=None,debug=False):
        profile=self.build_profile(user_id); k=top_k or self.config.final_k; ranked={}
        for interest_index,vector in enumerate(profile.positive_interests):
            scores,positions=self.semantic.index.search(vector.reshape(1,-1),self.config.candidate_k)
            for score,pos in zip(scores[0],positions[0]):
                if pos<0: continue
                work_id=self.semantic.mapping[pos]; item=ranked.setdefault(work_id,{'similarities':{},'matched':[]}); item['similarities'][interest_index]=float(score); item['matched'].append(interest_index)
        ids=list(ranked); books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}
        output=[]
        for work_id,data in ranked.items():
            if work_id in profile.interacted_ids: continue
            book=books.get(work_id)
            if not book: continue
            positive=max(data['similarities'].values()); negative=max((float(np.dot(self.features.vectors[work_id],v)) for v in profile.negative_interests),default=0.0)
            genre=sum(profile.genre_affinity.get(str(x),0) for x in self._values(book.content_tags)); author=profile.author_affinity.get(str(book.first_author),0); series=sum(profile.series_affinity.get(str(x),0) for x in self._values(book.series)); language=profile.language_affinity.get(str(book.language),0); length=profile.length_preference.get(str(book.length_category),0); year=0 if profile.year_mean is None or not book.earliest_known_publication_year else max(0,1-abs(book.earliest_known_publication_year-profile.year_mean)/50); quality=float(book.weighted_rating or book.average_rating or 0)/5
            components={'positive_semantic_similarity':positive,'negative_semantic_similarity':negative,'genre_affinity':genre,'author_affinity':author,'series_affinity':series,'language_affinity':language,'length_preference':length,'year_preference':year,'quality':quality}
            score=self.config.semantic_weight*positive-self.config.negative_weight*negative+self.config.genre_weight*genre+self.config.author_weight*author+self.config.series_weight*series+self.config.language_weight*language+self.config.length_weight*length+self.config.year_weight*year+self.config.quality_weight*quality
            output.append(Recommendation(work_id,score,components,data['matched']))
        return sorted(output,key=lambda x:(-x.score,x.work_id))[:k],profile,MODEL_VERSION
    @staticmethod
    def _values(raw):
        try:return json.loads(raw or '[]')
        except (TypeError,json.JSONDecodeError):return []
