from __future__ import annotations
import json, numpy as np
from dataclasses import dataclass,field
from ..models import Book,Interaction
from .config import RATING_STRENGTH
@dataclass
class UserContentProfile:
    user_id:str; positive_interests:list[np.ndarray]=field(default_factory=list); negative_interests:list[np.ndarray]=field(default_factory=list); genre_affinity:dict=field(default_factory=dict); author_affinity:dict=field(default_factory=dict); interacted_ids:set[int]=field(default_factory=set)
def values(raw):
    try:return json.loads(raw or '[]')
    except (TypeError,json.JSONDecodeError):return []
def build_profile(user_id,rows:list[Interaction],books:dict,vectors:dict,threshold=.72):
    p=UserContentProfile(user_id); p.interacted_ids={r.work_id for r in rows}; pos=[]; neg=[]
    for r in rows:
        b=books.get(r.work_id)
        if not b:continue
        strength=RATING_STRENGTH.get(r.rating or 3,0)+(0.7 if r.liked else 0)+(0.4 if r.followed else 0); bad=max(0,-RATING_STRENGTH.get(r.rating or 3,0))+(1 if r.disliked else 0)
        if strength>0 and r.work_id in vectors:pos.append(vectors[r.work_id])
        if bad>0 and r.work_id in vectors:neg.append(vectors[r.work_id])
        for tag in values(b.content_tags):p.genre_affinity[str(tag)]=p.genre_affinity.get(str(tag),0)+strength-bad
        if b.first_author:p.author_affinity[str(b.first_author)]=p.author_affinity.get(str(b.first_author),0)+strength-bad
    def cluster(items):
        out=[]
        for v in items:
            if not out or max(float(np.dot(v,x)) for x in out)<threshold:out.append(v)
        return out
    p.positive_interests=cluster(pos);p.negative_interests=cluster(neg);return p
