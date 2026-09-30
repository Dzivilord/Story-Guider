from typing import Literal
from pydantic import BaseModel, Field, model_validator

RetrievalMode = Literal['STRUCTURED', 'SEMANTIC', 'REFERENCE', 'HYBRID']
RankingField = Literal['rating', 'publication_year', 'pages']
RankingDirection = Literal['asc', 'desc']

class RankingPreference(BaseModel):
    model_config = {'extra': 'forbid'}
    field: RankingField
    direction: RankingDirection

class BookFilters(BaseModel):
    model_config = {'extra': 'forbid'}
    title: str | None = Field(...)
    authors: list[str] = Field(...)
    genres: list[str] = Field(...)
    publication_year_min: int | None = Field(...)
    publication_year_max: int | None = Field(...)
    rating_min: float | None = Field(...)
    rating_max: float | None = Field(...)
    length_categories: list[Literal['short','medium','long','very_long']] = Field(...)
    languages: list[str] = Field(...)
    series: list[str] = Field(...)

class BookSearchPlan(BaseModel):
    model_config = {'extra': 'forbid'}
    retrieval_mode: RetrievalMode
    structured_filters: BookFilters = Field(...)
    semantic_query: str | None = Field(...)
    reference_books: list[str] = Field(...)
    ranking_preferences: list[RankingPreference] = Field(...)
    reasoning_summary: str = Field(...)

    @model_validator(mode='after')
    def validate_mode(self):
        filter_values=self.structured_filters.model_dump(exclude_none=True)
        has_structured=any(value not in (None, '', [], {}) for value in filter_values.values())
        has_semantic = bool(self.semantic_query and self.semantic_query.strip())
        has_ranking = bool(self.ranking_preferences)
        has_structured = has_structured or has_ranking
        has_reference = bool(self.reference_books)
        if self.retrieval_mode == 'STRUCTURED' and (not has_structured or has_semantic or has_reference):
            raise ValueError('STRUCTURED plans must contain structured filters only')
        if self.retrieval_mode == 'SEMANTIC' and (not has_semantic or has_structured or has_reference):
            raise ValueError('SEMANTIC plans must contain semantic content only')
        if self.retrieval_mode == 'REFERENCE' and (not has_reference or has_structured or has_semantic):
            raise ValueError('REFERENCE plans must contain references only')
        if self.retrieval_mode == 'HYBRID' and sum((has_structured, has_semantic, has_reference)) < 2:
            raise ValueError('HYBRID plans must combine at least two retrieval signals')
        return self
