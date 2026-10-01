from typing import Literal
from pydantic import BaseModel, Field
class GuideRequest(BaseModel): user_id: str; query: str; top_k: int = Field(default=10, ge=1, le=50)
class GuidePlanRequest(BaseModel): query: str
class GuidePlan(BaseModel):
    mode: Literal['SEARCH','CONTENT_BASED','HYBRID']; tools_required: list[Literal['search_books','get_user_context','recommend_books','filter_candidates','score_candidates_for_user']]; search_query: str|None=None; recommendation_required: bool=False; genres:list[str]=[]; excluded_authors:list[str]=[]; exclude_followed:bool=False; publication_year_min:int|None=None; publication_year_max:int|None=None; pages_max:int|None=None; rating_min:float|None=None

class GuideResponse(BaseModel):
    user_id: str
    query: str
    plan: GuidePlan
    tools_used: list[str]
    results: list[dict]

