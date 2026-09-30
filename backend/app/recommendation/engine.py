from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from ..models import Book,Interaction
from ..search.semantic import SemanticBookRetriever
from .config import RecommendationConfig,MODEL_VERSION
from .profile import build_profile,values
@dataclass
class Recommendation:
    work_id:int;score:float;components:dict;matched_interests:list[int]
class ContentRecommendationService:
    def __init__(self,db,semantic_retriever=None,config=None):
        self.db=db;self.config=config or RecommendationConfig();self.semantic=semantic_retriever or SemanticBookRetriever();self.vectors={int(w):np.asarray(self.semantic.index.reconstruct(i),dtype='float32') for i,w in enumerate(self.semantic.mapping)}
    def recommend(self,user_id,top_k=None,debug=False):
        rows=self.db.query(Interaction).filter(Interaction.user_id==user_id).all();ids=[r.work_id for r in rows];books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {};p=build_profile(user_id,rows,books,self.vectors);pool={}
        for idx,v in enumerate(p.positive_interests):
            scores,positions=self.semantic.index.search(v.reshape(1,-1),self.config.candidate_k)
            for score,pos in zip(scores[0],positions[0]):
                if pos>=0:pool.setdefault(self.semantic.mapping[pos],{'similarity':{},'matched':[]});pool[self.semantic.mapping[pos]]['similarity'][idx]=float(score);pool[self.semantic.mapping[pos]]['matched'].append(idx)
        candidate_ids=list(pool);books={b.work_id:b for b in self.db.query(Book).filter(Book.work_id.in_(candidate_ids)).all()} if candidate_ids else {};out=[]
        for work_id,data in pool.items():
            if work_id in p.interacted_ids or work_id not in books:continue
            b=books[work_id];positive=max(data['similarity'].values());negative=max((float(np.dot(self.vectors[work_id],v)) for v in p.negative_interests),default=0);genre=sum(p.genre_affinity.get(str(x),0) for x in values(b.content_tags));author=p.author_affinity.get(str(b.first_author),0);quality=float(b.weighted_rating or b.average_rating or 0)/5;score=self.config.semantic_weight*positive-self.config.negative_weight*negative+self.config.genre_weight*genre+self.config.author_weight*author+self.config.quality_weight*quality;out.append(Recommendation(work_id,score,{'positive_semantic_similarity':positive,'negative_semantic_similarity':negative,'genre_affinity':genre,'author_affinity':author,'quality':quality},data['matched']))
        return sorted(out,key=lambda x:(-x.score,x.work_id))[:top_k or self.config.final_k],p,MODEL_VERSION
