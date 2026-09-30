from typing import Literal
from pydantic import BaseModel, Field
from .schemas import BookSearchPlan

ActionName=Literal['LOOKUP_BOOK','SEARCH_METADATA','SEMANTIC_SEARCH','SEMANTIC_REFERENCE_SEARCH','FILTER_CANDIDATES','SEMANTIC_WITHIN_CANDIDATES','COMBINE_CANDIDATES','GET_CANDIDATE_SUMMARY','FINISH']

class SearchAction(BaseModel):
    action: ActionName
    arguments: dict = Field(default_factory=dict)
    reasoning_summary: str=''
class CompactObservation(BaseModel):
    status: Literal['ok','error']
    message: str=''
    candidate_set_id: str|None=None
    candidate_count: int|None=None
    data: dict = Field(default_factory=dict)
class SearchAgentState(BaseModel):
    user_query: str
    plan: BookSearchPlan
    current_candidate_set_id: str|None=None
    candidate_count: int=0
    resolved_references: dict[str,dict]=Field(default_factory=dict)
    observations: list[CompactObservation]=Field(default_factory=list)
    executed_actions: list[SearchAction]=Field(default_factory=list)
    iteration: int=0
    status: Literal['PLANNING','EXECUTING','DONE','FAILED']='PLANNING'
