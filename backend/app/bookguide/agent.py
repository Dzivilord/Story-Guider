from __future__ import annotations
import re
from .schemas import GuidePlan,GuideResponse
from ..search.model_provider import provider_from_config,ModelProvider
PERSONAL=('i liked','i like','my favorite','my usual','my taste','my reading','i have read','read before','reading history','usually read','i would','i tend to','i previously','books i','what i','i dislike','i disliked','usually dislike','disliked before','i follow','previously enjoyed','normally enjoy','reading preferences','tend to like')
SEARCH=('published','after ','before ','under ','pages','novels','books by ','about ','female protagonist','dark atmosphere','artificial intelligence','human consciousness','space exploration','dragons','fantasy','mystery','science fiction','historical fiction')
class BookGuide:
    def __init__(self,db=None,provider:ModelProvider|None=None):
        self.tools=None
        self.provider=provider or provider_from_config()
        if db is not None:
            from .tools import BookGuideTools
            self.tools=BookGuideTools(db)
    def plan(self,query:str)->GuidePlan:
        prompt='''You are the BookGuide planner. Classify the user's request into exactly one mode: SEARCH, CONTENT_BASED, or HYBRID. SEARCH is ordinary non-personalized search and uses only search_books. CONTENT_BASED uses get_user_context and recommend_books, whose seeds come only from the user's interactions. HYBRID uses search_books to create a query candidate pool, get_user_context to load taste, filter_candidates for hard constraints/exclusions, and score_candidates_for_user to rerank that pool. Use HYBRID whenever explicit search criteria or a named reference coexists with personalization. Extract only explicit genres, author exclusions, year/page/rating constraints, and followed/read exclusions. Do not retrieve books and do not invent user preferences. Return only the GuidePlan JSON.'''
        try:
            return GuidePlan.model_validate(self.provider.complete_structured(prompt,query,GuidePlan.model_json_schema()))
        except Exception:
            return self._fallback_plan(query)

    def _fallback_plan(self,query:str)->GuidePlan:
        text=query.casefold().strip(); personal=any(x in text for x in PERSONAL); search=any(x in text for x in SEARCH)
        named=bool(re.search(r'\b(?:like|similar to)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,5}',query)); search=search or named
        mode='HYBRID' if personal and search else 'CONTENT_BASED' if personal else 'SEARCH'; tools=['search_books','get_user_context','filter_candidates','score_candidates_for_user'] if mode=='HYBRID' else ['get_user_context','recommend_books'] if mode=='CONTENT_BASED' else ['search_books']
        genres=[]
        for g in ('fantasy','mystery','science fiction','historical fiction'):
            if g in text: genres.append('Science Fiction' if g=='science fiction' else g.title())
        match=re.search(r'(?:avoid|nothing from|not from|excluding)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})',query)
        excluded=[match.group(1).strip()] if match else []
        followed="don't show books i've already followed" in text or 'do not show books i\'ve already followed' in text or 'do not recommend what i follow' in text
        return GuidePlan(mode=mode,tools_required=tools,search_query=query if mode!='CONTENT_BASED' else None,recommendation_required=personal,genres=genres,excluded_authors=excluded,exclude_followed=followed)
    def run(self,user_id,query,top_k=10,debug=False)->GuideResponse:
        if self.tools is None: raise RuntimeError('BookGuide requires a database for execution')
        plan=self.plan(query)
        if debug: print('\nPLAN\n',plan.model_dump_json(indent=2))
        if plan.mode=='SEARCH':
            response=self.tools.search_books(query,top_k); used=['search_books']; results=response.results
            if debug: print(f'TOOL search_books -> {len(results)} candidates')
            return GuideResponse(user_id=user_id,query=query,plan=plan,tools_used=used,results=results)
        used=[]
        if plan.mode=='HYBRID':
            search_response=self.tools.search_books(query,self.tools.search.candidate_k if hasattr(self.tools.search,'candidate_k') else max(top_k*10,100)); used.append('search_books'); ids=[x['work_id'] for x in search_response.results]
            if debug: print(f'TOOL search_books -> {len(ids)} candidates')
            self.tools.get_user_context(user_id); used.append('get_user_context')
            ids=self.tools.filter_candidates(ids,genres=plan.genres,publication_year_min=plan.publication_year_min,publication_year_max=plan.publication_year_max,pages_max=plan.pages_max,rating_min=plan.rating_min,excluded_authors=plan.excluded_authors,exclude_followed=plan.exclude_followed,user_id=user_id); used.append('filter_candidates')
            if debug: print(f'TOOL filter_candidates -> {len(ids)} candidates')
            items=self.tools.score_candidates_for_user(user_id,ids,top_k); used.append('score_candidates_for_user')
            if debug: print(f'TOOL score_candidates_for_user -> {len(items)} candidates')
        else:
            self.tools.get_user_context(user_id); used.append('get_user_context'); items,_,_=self.tools.recommend_books(user_id,top_k,plan.genres,plan.excluded_authors,plan.exclude_followed); used.append('recommend_books')
        from ..models import Book
        ids=[x.work_id for x in items]; books={b.work_id:b for b in self.tools.db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else []
        results=[{'work_id':x.work_id,'title':books[x.work_id].title,'first_author':books[x.work_id].first_author,'description':books[x.work_id].description,'content_tags':__import__('json').loads(books[x.work_id].content_tags or '[]'),'score':x.score,'components':x.components,'matched_interests':x.matched_interests} for x in items if x.work_id in books]
        if debug:
            print('FINAL CANDIDATES')
            for rank,item in enumerate(results,1): print(f'  {rank:02d}. {item["work_id"]} {item["title"]} score={item["score"]:.4f}')
        return GuideResponse(user_id=user_id,query=query,plan=plan,tools_used=used,results=results)
