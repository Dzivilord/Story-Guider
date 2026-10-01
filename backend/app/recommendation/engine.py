from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from ..models import Book, Interaction
from ..search.semantic import SemanticBookRetriever
from .config import RecommendationConfig, MODEL_VERSION
from .profile import build_profile, values

@dataclass
class Recommendation:
    work_id: int
    score: float
    components: dict
    matched_interests: list[int]

class ContentRecommendationService:
    def __init__(self, db, semantic_retriever=None, config=None):
        self.db=db; self.config=config or RecommendationConfig(); self.semantic=semantic_retriever or SemanticBookRetriever()
        self.vectors={int(work_id):np.asarray(self.semantic.index.reconstruct(pos),dtype='float32') for pos,work_id in enumerate(self.semantic.mapping)}

    def build_profile(self,user_id):
        rows=self.db.query(Interaction).filter(Interaction.user_id==user_id).all(); ids=[r.work_id for r in rows]
        books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}
        return build_profile(user_id,rows,books,self.vectors)

    def _score(self, profile, book, similarity_by_interest=None):
        vector=self.vectors.get(book.work_id)
        positive=max((similarity_by_interest or {}).values(),default=max((float(np.dot(vector,v)) for v in profile.positive_interests),default=0.0)) if vector is not None else 0.0
        negative=max((float(np.dot(vector,v)) for v in profile.negative_interests),default=0.0) if vector is not None else 0.0
        genre=sum(profile.genre_affinity.get(str(x),0.0) for x in values(book.content_tags)); author=profile.author_affinity.get(str(book.first_author),0.0)
        quality=float(book.weighted_rating or book.average_rating or 0.0)/5.0
        components={'positive_semantic_similarity':positive,'negative_semantic_similarity':negative,'genre_affinity':genre,'author_affinity':author,'quality':quality}
        score=self.config.semantic_weight*positive-self.config.negative_weight*negative+self.config.genre_weight*genre+self.config.author_weight*author+self.config.quality_weight*quality
        return score,components

    def score_candidates_for_user(self,user_id,work_ids,top_k=None):
        profile=self.build_profile(user_id); ids=list(dict.fromkeys(int(x) for x in work_ids)); books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}; results=[]
        for work_id in ids:
            book=books.get(work_id)
            if not book or work_id in profile.interacted_ids: continue
            score,components=self._score(profile,book); results.append(Recommendation(work_id,score,components,[]))
        return sorted(results,key=lambda x:(-x.score,x.work_id))[:top_k] if top_k else sorted(results,key=lambda x:(-x.score,x.work_id))

    def recommend(self,user_id,top_k=None,genres=None,excluded_authors=None,exclude_followed=False):
        rows=self.db.query(Interaction).filter(Interaction.user_id==user_id).all(); profile=self.build_profile(user_id); pool={}
        for idx,vector in enumerate(profile.positive_interests):
            scores,positions=self.semantic.index.search(vector.reshape(1,-1),self.config.candidate_k)
            for score,pos in zip(scores[0],positions[0]):
                if pos>=0: pool.setdefault(self.semantic.mapping[pos],{})[idx]=float(score)
        ids=list(pool); books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}; followed={r.work_id for r in rows if r.followed}; out=[]
        for work_id,similarities in pool.items():
            book=books.get(work_id)
            if not book or work_id in profile.interacted_ids or (exclude_followed and work_id in followed): continue
            if genres and not any(str(g).casefold() in {str(x).casefold() for x in values(book.content_tags)} for g in genres): continue
            if excluded_authors and any(str(a).casefold() in str(book.first_author or '').casefold() for a in excluded_authors): continue
            score,components=self._score(profile,book,similarities); out.append(Recommendation(work_id,score,components,list(similarities)))
        return sorted(out,key=lambda x:(-x.score,x.work_id))[:top_k or self.config.final_k],profile,MODEL_VERSION
