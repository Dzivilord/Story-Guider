from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, select, text
import json
from .database import Base, engine, get_db
from .models import Book, User, Interaction
from .config import GENRES
from datetime import datetime
from .searchservice import BookSearchService
from .recommendation.engine import ContentRecommendationService
from .bookguide.agent import BookGuide
from .bookguide.schemas import GuideRequest, GuidePlanRequest

Base.metadata.create_all(engine); app=FastAPI(title='Goodreads RecSys API')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000','http://127.0.0.1:3000'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
class UserIn(BaseModel): name:str
class InteractionIn(BaseModel): user_id:str; work_id:int; interaction_type:str
class RecommendationIn(BaseModel): query: str; top_k: int = 10; user_id: str | None = None
class RatingIn(BaseModel): user_id: str; work_id: int; rating: int
class UserRecommendationIn(BaseModel): top_k: int = 20; debug: bool = False
def user_data(db,u): return {'id':u.id,'name':u.name,'created_at':u.created_at}
@app.get('/health')
def health(): return {'status':'ok'}
@app.get('/genres')
def genres(db:Session=Depends(get_db)):
    """Return only the 40 most common tags; all tags remain stored in books."""
    try:
        rows=db.execute(text("""
            SELECT json_each.value AS genre, COUNT(DISTINCT books.work_id) AS book_count
            FROM books, json_each(books.content_tags)
            WHERE json_each.type = 'text' AND TRIM(json_each.value) <> ''
            GROUP BY json_each.value
            ORDER BY book_count DESC, genre COLLATE NOCASE ASC
            LIMIT 40
        """)).all()
        return [row.genre for row in rows]
    except Exception:
        # Compatibility fallback for SQLite builds without JSON1.
        counts={}
        for raw, in db.query(Book.content_tags).filter(Book.content_tags.isnot(None)).all():
            try:
                for genre in set(json.loads(raw or '[]')):
                    if isinstance(genre,str) and genre.strip(): counts[genre]=counts.get(genre,0)+1
            except (TypeError, json.JSONDecodeError): pass
        return [genre for genre, _ in sorted(counts.items(), key=lambda item:(-item[1], item[0].lower()))[:40]]
@app.get('/books/search')
def search(q: str=Query(''), user_id:str|None=None, genres:str|None=None, page:int=Query(1,ge=1), page_size:int=Query(10,ge=1,le=50), db:Session=Depends(get_db)):
    q=q.strip()
    selected=[x.strip() for x in (genres or '').split(',') if x.strip()]
    query=db.query(Book)
    if q:
        like=f'%{q.lower()}%'; query=query.filter(or_(func.lower(Book.title).like(like),func.lower(Book.first_author).like(like)))
    # Multi-select is an intersection: a book must contain every selected tag.
    # The text query and genre constraints are combined with AND.
    for genre in selected:
        query=query.filter(Book.content_tags.like(f'%"{genre}"%'))
    total=query.count(); rows=query.order_by(Book.title).offset((page-1)*page_size).limit(page_size).all()
    states={i.work_id:i for i in db.query(Interaction).filter(Interaction.user_id==user_id).all()} if user_id else {}
    items=[{'work_id':b.work_id,'title':b.title,'first_author':b.first_author if b.first_author and b.first_author.strip() and b.first_author.lower()!='unknown' else None,'earliest_known_publication_year':b.earliest_known_publication_year,'description':b.description,'content_tags':json.loads(b.content_tags or '[]'),'series':json.loads(b.series or '[]'),'interaction':('like' if states.get(b.work_id) and states[b.work_id].liked else 'dislike' if states.get(b.work_id) and states[b.work_id].disliked else 'follow' if states.get(b.work_id) and states[b.work_id].followed else None),'user_rating':states.get(b.work_id).rating if states.get(b.work_id) else None} for b in rows]
    import math
    return {'items':items,'page':page,'page_size':page_size,'total':total,'total_pages':math.ceil(total/page_size) if total else 0}
@app.post('/books/recommend')
def recommend_books(payload: RecommendationIn, db:Session=Depends(get_db)):
    """Natural-language recommendations, separate from title/author search."""
    if not payload.query.strip(): raise HTTPException(400, 'Recommendation query cannot be empty')
    try:
        response = BookSearchService(db).search(payload.query, top_k=min(max(payload.top_k, 1), 50))
        if payload.user_id:
            states={i.work_id:i for i in db.query(Interaction).filter(Interaction.user_id==payload.user_id).all()}
            for item in response.results:
                state=states.get(item['work_id']); item['interaction']=('like' if state and state.liked else 'dislike' if state and state.disliked else 'follow' if state and state.followed else None); item['user_rating']=state.rating if state else None
        return {'query':response.query,'plan':response.plan.model_dump(),'results':response.results,'diagnostics':response.diagnostics}
    except Exception as error:
        raise HTTPException(500, f'Recommendation search failed: {error}') from error
@app.get('/users')
def users(db:Session=Depends(get_db)): return [user_data(db,u) for u in db.query(User).order_by(User.id).all()]
@app.post('/users/{user_id}/recommendations')
def personalized_recommendations(user_id:str,payload:UserRecommendationIn,db:Session=Depends(get_db)):
    if not db.get(User,user_id): raise HTTPException(404,'User not found')
    try:
        items,profile,version=ContentRecommendationService(db).recommend(user_id,min(max(payload.top_k,1),50))
        ids=[x.work_id for x in items]; books={b.work_id:b for b in db.query(Book).filter(Book.work_id.in_(ids)).all()} if ids else {}
        results=[]
        for item in items:
            b=books[item.work_id]; row={'work_id':b.work_id,'title':b.title,'first_author':b.first_author,'description':b.description,'average_rating':b.average_rating,'score':item.score,'matched_interests':item.matched_interests}
            if payload.debug:row['components']=item.components
            results.append(row)
        return {'user_id':user_id,'model_version':version,'interaction_count':len(profile.interacted_ids),'results':results}
    except (FileNotFoundError,OSError,ValueError,ImportError) as error:
        raise HTTPException(503,f'Recommendation engine unavailable: {error}') from error
@app.post('/bookguide')
def bookguide(payload:GuideRequest,db:Session=Depends(get_db)):
    if not db.get(User,payload.user_id): raise HTTPException(404,'User not found')
    try: return BookGuide(db).run(payload.user_id,payload.query,payload.top_k).model_dump()
    except (FileNotFoundError,OSError,ValueError,ImportError) as error: raise HTTPException(503,f'BookGuide unavailable: {error}') from error
@app.post('/bookguide/plan')
def bookguide_plan(payload:GuidePlanRequest):
    return BookGuide().plan(payload.query).model_dump()
@app.post('/users')
def create_user(payload:UserIn,db:Session=Depends(get_db)):
    n=db.query(User).count()+1; uid=f'U{n:03d}'
    while db.get(User,uid): n+=1; uid=f'U{n:03d}'
    u=User(id=uid,name=payload.name.strip()); db.add(u); db.commit(); return user_data(db,u)
@app.get('/users/{user_id}')
def get_user(user_id:str,db:Session=Depends(get_db)):
    u=db.get(User,user_id)
    if not u: raise HTTPException(404,'User not found')
    return user_data(db,u)
@app.get('/interactions')
def interactions(user_id:str,db:Session=Depends(get_db)): return [{'user_id':i.user_id,'work_id':i.work_id,'liked':i.liked,'disliked':i.disliked,'followed':i.followed,'rating':i.rating} for i in db.query(Interaction).filter_by(user_id=user_id).all()]
@app.put('/interactions')
def set_interaction(p:InteractionIn,db:Session=Depends(get_db)):
    if p.interaction_type not in ('like','dislike','follow'): raise HTTPException(400,'interaction_type must be like, dislike, or follow')
    if not db.get(User,p.user_id) or not db.get(Book,p.work_id): raise HTTPException(404,'User or book not found')
    i=db.get(Interaction,(p.user_id,p.work_id)) or Interaction(user_id=p.user_id,work_id=p.work_id); db.add(i)
    field={'like':'liked','dislike':'disliked','follow':'followed'}[p.interaction_type]; setattr(i,field,not getattr(i,field)); i.updated_at=datetime.utcnow()
    db.commit(); return {'interaction':p.interaction_type if getattr(i,field) else None, 'liked':i.liked, 'disliked':i.disliked, 'followed':i.followed, 'rating':i.rating}
@app.put('/ratings')
def set_rating(p:RatingIn,db:Session=Depends(get_db)):
    if p.rating < 1 or p.rating > 5: raise HTTPException(400,'rating must be between 1 and 5')
    if not db.get(User,p.user_id) or not db.get(Book,p.work_id): raise HTTPException(404,'User or book not found')
    item=db.get(Interaction,(p.user_id,p.work_id)) or Interaction(user_id=p.user_id,work_id=p.work_id); db.add(item); item.rating=p.rating; item.updated_at=datetime.utcnow(); db.commit(); return {'user_rating':p.rating}
@app.delete('/interactions/{user_id}/{work_id}')
def delete_interaction(user_id:str,work_id:str,db:Session=Depends(get_db)):
    i=db.get(Interaction,(user_id,work_id));
    if i: db.delete(i); db.commit()
    return {'ok':True}
