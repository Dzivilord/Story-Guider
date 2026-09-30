from dataclasses import dataclass
from uuid import uuid4
@dataclass
class CandidateSet:
    id:str; book_ids:list[int]; scores:dict[int,float]|None=None; source:str=''
class CandidateStore:
    def __init__(self): self._sets={}
    def create(self,book_ids,scores=None,source=''):
        cid=f'cand_{uuid4().hex[:10]}'; self._sets[cid]=CandidateSet(cid,list(dict.fromkeys(book_ids)),scores,source); return self._sets[cid]
    def get(self,cid):
        if cid not in self._sets: raise KeyError(f'Unknown candidate set: {cid}')
        return self._sets[cid]
    def combine(self,ids,strategy):
        sets=[self.get(x) for x in ids]; values=[set(x.book_ids) for x in sets]
        if strategy=='intersection': result=[x for x in sets[0].book_ids if all(x in value for value in values[1:])]
        else: result=[]
        if strategy!='intersection':
            for candidate_set in sets:
                result.extend(x for x in candidate_set.book_ids if x not in result)
        scores={}
        for candidate_set in sets:
            if candidate_set.scores:
                scores.update({x:candidate_set.scores[x] for x in candidate_set.scores if x in result})
        return self.create(result,scores=scores or None,source=f'combine:{strategy}')
