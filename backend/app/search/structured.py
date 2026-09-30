from __future__ import annotations

import json
from dataclasses import dataclass
from sqlalchemy import or_, func, exists, select
from .schemas import BookFilters
from ..models import Book


@dataclass(frozen=True)
class StructuredSearchResult:
    work_id: int
    title: str
    author: str | None
    publication_year: int | None
    average_rating: float | None


class StructuredBookRetriever:
    def __init__(self, db):
        self.db = db

    def search(self, filters: BookFilters, limit: int = 50, work_ids: list[int] | None = None) -> list[StructuredSearchResult]:
        limit = max(1, min(int(limit), 1000))
        q = self.db.query(Book)
        if work_ids is not None:
            if not work_ids:
                return []
            q = q.filter(Book.work_id.in_(work_ids))
        if filters.title:
            q = q.filter(func.lower(Book.title).like(f"%{filters.title.strip().lower()}%"))
        if filters.authors:
            q = q.filter(or_(*(func.lower(Book.first_author).like(f"%{x.strip().lower()}%") for x in filters.authors if x.strip())))
        if filters.genres:
            q = q.filter(self._json_any(Book.content_tags, filters.genres))
        if filters.series:
            q = q.filter(self._json_any(Book.series, filters.series))
        if filters.publication_year_min is not None:
            q = q.filter(Book.earliest_known_publication_year >= filters.publication_year_min)
        if filters.publication_year_max is not None:
            q = q.filter(Book.earliest_known_publication_year <= filters.publication_year_max)
        if filters.rating_min is not None:
            q = q.filter(Book.average_rating >= filters.rating_min)
        if filters.rating_max is not None:
            q = q.filter(Book.average_rating <= filters.rating_max)
        if filters.length_categories:
            q = q.filter(Book.length_category.in_(filters.length_categories))
        if filters.languages:
            q = q.filter(Book.language.in_(filters.languages))
        rows = q.order_by(Book.average_rating.desc()).limit(limit).all()
        return [StructuredSearchResult(b.work_id, b.title, b.first_author, b.earliest_known_publication_year, b.average_rating) for b in rows]

    def filter_candidates(self, work_ids: list[int], filters: BookFilters) -> list[StructuredSearchResult]:
        """Apply hard metadata constraints without changing candidate relevance order."""
        return self.search(filters, limit=max(len(work_ids), 1), work_ids=work_ids)

    @staticmethod
    def _json_any(column, values):
        """Exact membership in a JSON array; OR within one filter group."""
        # json_each is supported by the SQLite build used by this project.
        requested = [x.strip() for x in values if x and x.strip()]
        if not requested:
            return True
        json_items = func.json_each(column).table_valued("value")
        item = select(1).select_from(json_items).where(json_items.c.value.in_(requested))
        return exists(item)
