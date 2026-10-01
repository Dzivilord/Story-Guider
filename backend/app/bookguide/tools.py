from ..recommendation.engine import ContentRecommendationService
from ..searchservice import BookSearchService
from ..models import Book, Interaction

class BookGuideTools:
    def __init__(self, db):
        self.db=db
        self.search=BookSearchService(db)
        self.recommendation=ContentRecommendationService(db)
    def get_user_context(self,user_id):
        profile=self.recommendation.build_profile(user_id)
        rows=self.db.query(Interaction).filter_by(user_id=user_id).all()
        return {'user_id':user_id,'interaction_count':len(profile.interacted_ids),'positive_interests':len(profile.positive_interests),'negative_interests':len(profile.negative_interests),'liked_work_ids':[r.work_id for r in rows if r.liked],'disliked_work_ids':[r.work_id for r in rows if r.disliked],'followed_work_ids':[r.work_id for r in rows if r.followed],'rated_work_ids':[r.work_id for r in rows if r.rating is not None],'interacted_work_ids':list(profile.interacted_ids)}
    def recommend_books(self,user_id,top_k,genres=None,excluded_authors=None,exclude_followed=False):
        return self.recommendation.recommend(user_id,top_k,genres=genres,excluded_authors=excluded_authors,exclude_followed=exclude_followed)
    def search_books(self,query,top_k):
        return self.search.search(query,top_k=top_k)
    def filter_candidates(self,work_ids,genres=None,publication_year_min=None,publication_year_max=None,pages_max=None,rating_min=None,excluded_authors=None,excluded_work_ids=None,exclude_followed=False,user_id=None):
        ids=list(dict.fromkeys(int(x) for x in work_ids)); q=self.db.query(Book).filter(Book.work_id.in_(ids)) if ids else None
        if not q:return []
        if genres:
            for genre in genres:q=q.filter(Book.content_tags.like(f'%"{genre}"%'))
        if publication_year_min is not None:q=q.filter(Book.earliest_known_publication_year>=publication_year_min)
        if publication_year_max is not None:q=q.filter(Book.earliest_known_publication_year<=publication_year_max)
        if pages_max is not None:q=q.filter(Book.pages<=pages_max)
        if rating_min is not None:q=q.filter(Book.average_rating>=rating_min)
        if excluded_work_ids:q=q.filter(~Book.work_id.in_(excluded_work_ids))
        if excluded_authors:
            for author in excluded_authors:q=q.filter(~Book.first_author.ilike(f'%{author}%'))
        if exclude_followed and user_id:
            from ..models import Interaction
            followed=[r.work_id for r in self.db.query(Interaction.work_id).filter(Interaction.user_id==user_id,Interaction.followed.is_(True)).all()]
            if followed:q=q.filter(~Book.work_id.in_(followed))
        return [b.work_id for b in q.all()]
    def score_candidates_for_user(self,user_id,work_ids,top_k=None):
        return self.recommendation.score_candidates_for_user(user_id,work_ids,top_k)
