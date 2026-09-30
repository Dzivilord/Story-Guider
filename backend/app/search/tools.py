import json
import logging
from sqlalchemy import or_, func
from .candidate_store import CandidateStore
from .agent_schemas import CompactObservation
from ..models import Book
from .semantic import SemanticBookRetriever
from .structured import StructuredBookRetriever
from .schemas import BookFilters

ALLOWED_FIELDS={'work_id','title','description','content_tags','series','first_author','earliest_known_publication_year','pages','language'}
class SearchTools:
    def __init__(self,db,store=None,semantic_retriever=None):
        self.db=db; self.store=store or CandidateStore(); self.structured_retriever=StructuredBookRetriever(db); self.semantic_retriever=semantic_retriever
        if self.semantic_retriever is None:
            try: self.semantic_retriever=SemanticBookRetriever()
            except (FileNotFoundError, OSError, ValueError, ImportError): self.semantic_retriever=None
    def lookup_book(self,title,fields):
        if not fields or any(x not in ALLOWED_FIELDS for x in fields): return CompactObservation(status='error',message='Unsupported lookup field')
        books=self.db.query(Book).filter(func.lower(Book.title).like(f'%{title.lower().strip()}%')).limit(5).all()
        if not books:return CompactObservation(status='error',message='REFERENCE_NOT_FOUND')
        if len(books)>1:return CompactObservation(status='error',message='REFERENCE_AMBIGUOUS',data={'matches':[{'work_id':b.work_id,'title':b.title} for b in books[:3]]})
        b=books[0]; data={}
        for f in fields:
            value=getattr(b,f)
            if f in ('content_tags','series'):
                try:value=json.loads(value or '[]')
                except json.JSONDecodeError:value=[]
            data[f]=value
        return CompactObservation(status='ok',message='Book found',data=data)
    def search_metadata(self,**kwargs):
        filters=BookFilters(title=kwargs.get('title'), authors=kwargs.get('authors',[]), genres=kwargs.get('genres',[]), publication_year_min=kwargs.get('publication_year_min'), publication_year_max=kwargs.get('publication_year_max'), rating_min=kwargs.get('rating_min'), rating_max=kwargs.get('rating_max'), length_categories=kwargs.get('length_categories',[]), languages=kwargs.get('languages',[]), series=kwargs.get('series',[]))
        rows=self.structured_retriever.search(filters, kwargs.get('limit',10000)); c=self.store.create([x.work_id for x in rows],source='metadata')
        return CompactObservation(status='ok',message='Metadata search complete',candidate_set_id=c.id,candidate_count=len(c.book_ids))
        # Legacy query implementation retained below for reference.
        q=self.db.query(Book)
        authors=kwargs.get('authors',[]); genres=kwargs.get('genres',[]); languages=kwargs.get('languages',[])
        if authors:q=q.filter(or_(*(func.lower(Book.first_author).like(f'%{x.lower()}%') for x in authors)))
        if genres:
            for g in genres:q=q.filter(Book.content_tags.like(f'%"{g}"%'))
        if languages:q=q.filter(Book.language.in_(languages))
        if kwargs.get('publication_year_min') is not None:q=q.filter(Book.earliest_known_publication_year>=kwargs['publication_year_min'])
        if kwargs.get('rating_min') is not None:q=q.filter(Book.average_rating>=kwargs['rating_min'])
        if kwargs.get('rating_max') is not None:q=q.filter(Book.average_rating<=kwargs['rating_max'])
        if kwargs.get('length_categories'):q=q.filter(Book.length_category.in_(kwargs['length_categories']))
        ranking=kwargs.get('ranking_preferences', [])
        ranking_columns={'rating': Book.average_rating, 'publication_year': Book.earliest_known_publication_year, 'pages': Book.pages}
        for preference in ranking:
            field=preference.get('field') if isinstance(preference, dict) else None
            direction=preference.get('direction') if isinstance(preference, dict) else None
            column=ranking_columns.get(field)
            if column is not None:
                q=q.order_by(column.asc() if direction == 'asc' else column.desc())
        rows=q.with_entities(Book.work_id).limit(10000).all(); c=self.store.create([x[0] for x in rows],source='metadata')
        return CompactObservation(status='ok',message='Metadata search complete',candidate_set_id=c.id,candidate_count=len(c.book_ids))
    def filter_candidates(self,candidate_set_id,**kwargs):
        base=self.store.get(candidate_set_id); q=self.db.query(Book).filter(Book.work_id.in_(base.book_ids)); result=self.search_metadata(**kwargs); allowed=set(self.store.get(result.candidate_set_id).book_ids); c=self.store.create([x for x in base.book_ids if x in allowed],source='filtered'); return CompactObservation(status='ok',message='Candidate set filtered',candidate_set_id=c.id,candidate_count=len(c.book_ids))
    def semantic_search(self,query,top_k=20):
        if not self.semantic_retriever: return CompactObservation(status='error',message='SEMANTIC_INDEX_UNAVAILABLE')
        results=self.semantic_retriever.search(query,int(top_k)); ids=[r.work_id for r in results]; scores={r.work_id:r.semantic_score for r in results}; c=self.store.create(ids,scores=scores,source='semantic')
        return CompactObservation(status='ok',message='Semantic search complete',candidate_set_id=c.id,candidate_count=len(ids),data={'top_scores':scores})
    def semantic_reference_search(self, **kwargs):
        logging.getLogger(__name__).warning('Reference semantic search requested but is not implemented; skipping: %s', kwargs)
        return CompactObservation(status='ok',message='REFERENCE_SEARCH_SKIPPED',data={'logged':True})
    def semantic_within_candidates(self,candidate_set_id,query,top_k=20):
        base=self.store.get(candidate_set_id); result=self.semantic_search(query,top_k)
        if result.status=='error': return result
        semantic=self.store.get(result.candidate_set_id); ids=[x for x in semantic.book_ids if x in set(base.book_ids)]; scores={x:semantic.scores[x] for x in ids}; c=self.store.create(ids,scores=scores,source='semantic_within_candidates')
        return CompactObservation(status='ok',message='Semantic search within candidates complete',candidate_set_id=c.id,candidate_count=len(ids),data={'top_scores':scores})
    def execute(self,action,arguments):
        if action=='LOOKUP_BOOK':return self.lookup_book(**arguments)
        if action=='SEARCH_METADATA':return self.search_metadata(**arguments)
        if action=='FILTER_CANDIDATES':return self.filter_candidates(**arguments)
        if action=='SEMANTIC_REFERENCE_SEARCH': return self.semantic_reference_search(**arguments)
        if action=='SEMANTIC_SEARCH':
            query=arguments.get('query') or arguments.get('semantic_query')
            if not query: return CompactObservation(status='error',message='SEMANTIC_QUERY_REQUIRED')
            return self.semantic_search(query,arguments.get('top_k',20))
        if action=='SEMANTIC_WITHIN_CANDIDATES': return self.semantic_within_candidates(**arguments)
        if action=='COMBINE_CANDIDATES':
            if not arguments.get('candidate_set_ids') or len(arguments['candidate_set_ids']) < 2:
                return CompactObservation(status='error',message='COMBINE_REQUIRES_TWO_CANDIDATE_SET_IDS')
            c=self.store.combine(arguments['candidate_set_ids'],arguments['strategy']); return CompactObservation(status='ok',message='Candidate sets combined',candidate_set_id=c.id,candidate_count=len(c.book_ids))
        if action=='GET_CANDIDATE_SUMMARY':
            c=self.store.get(arguments['candidate_set_id']); return CompactObservation(status='ok',message='Candidate summary',candidate_set_id=c.id,candidate_count=len(c.book_ids))
        return CompactObservation(status='error',message='Unsupported action')
