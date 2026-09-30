"""End-to-end natural-language book search orchestration."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from .models import Book
from .search.fusion import CandidateFusionService, RankedCandidate
from .search.query_router import BookSearchRouter
from .search.references import ReferenceBookResolver
from .search.schemas import BookSearchPlan
from .search.semantic import SemanticBookRetriever
from .search.structured import StructuredBookRetriever

log = logging.getLogger(__name__)


@dataclass
class BookSearchResponse:
    query: str
    plan: BookSearchPlan
    results: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class BookSearchService:
    def __init__(self, db, router=None, semantic_retriever=None, reference_resolver=None,
                 candidate_k: int | None = None, reference_k: int | None = None, rrf_k: int | None = None):
        self.db = db
        self.router = router or BookSearchRouter()
        self.semantic = semantic_retriever
        if self.semantic is None:
            try:
                self.semantic = SemanticBookRetriever()
            except (FileNotFoundError, OSError, ValueError, ImportError):
                self.semantic = None
        self.references = reference_resolver or ReferenceBookResolver(db, self.semantic) if self.semantic else None
        self.structured = StructuredBookRetriever(db)
        self.fusion = CandidateFusionService(rrf_k or int(os.getenv("SEARCH_RRF_K", "60")))
        self.candidate_k = candidate_k or int(os.getenv("SEARCH_SEMANTIC_CANDIDATE_K", "200"))
        self.reference_k = reference_k or int(os.getenv("SEARCH_REFERENCE_CANDIDATE_K", "200"))

    @staticmethod
    def _has_filters(plan: BookSearchPlan) -> bool:
        values = plan.structured_filters.model_dump(exclude_none=True)
        return any(value not in (None, "", [], {}) for value in values.values()) or bool(plan.ranking_preferences)

    def search(self, query: str, top_k: int = 20, debug: bool = False) -> BookSearchResponse:
        plan = self.router.route(query)
        has_structured = self._has_filters(plan)
        has_semantic = bool(plan.semantic_query and plan.semantic_query.strip())
        has_references = bool(plan.reference_books)
        diagnostics: dict[str, Any] = {"routing": {"structured": has_structured, "semantic": has_semantic, "references": has_references}, "candidate_counts": {}, "references": []}
        if debug:
            self._print_debug_header(query, plan, diagnostics["routing"])

        # Structured-only retrieval keeps the existing rating ordering.
        if has_structured and not has_semantic and not has_references:
            rows = self.structured.search(plan.structured_filters, max(1, top_k))
            ids = [row.work_id for row in rows]
            diagnostics["candidate_counts"]["structured"] = len(ids)
            response = BookSearchResponse(query, plan, self._load_books(ids), diagnostics if debug else {})
            if debug:
                self._print_candidates(response.results, diagnostics)
            return response

        ranked_lists: list[list[RankedCandidate]] = []
        excluded: set[int] = set()
        if has_semantic:
            if self.semantic is None:
                diagnostics["semantic_error"] = "SEMANTIC_INDEX_UNAVAILABLE"
            else:
                results = self.semantic.search(plan.semantic_query, self.candidate_k)
                ranked_lists.append([RankedCandidate(x.work_id, "semantic", i, x.semantic_score) for i, x in enumerate(results, 1)])
                diagnostics["candidate_counts"]["semantic"] = len(results)

        if has_references:
            if self.references is None:
                diagnostics["reference_error"] = "REFERENCE_INDEX_UNAVAILABLE"
            else:
                for raw_title in plan.reference_books:
                    info = {"raw": raw_title}
                    try:
                        reference = self.references.resolve(raw_title)
                        info.update(
                            status="resolved",
                            title=reference.title,
                            author=reference.author,
                            description=reference.description,
                            genres=reference.genres,
                            work_id=reference.work_id,
                            source=reference.source,
                        )
                        if reference.work_id is not None:
                            excluded.add(reference.work_id)
                        results = self.references.search_candidates([reference], self.reference_k)
                        ranked_lists.append([RankedCandidate(work_id, f"reference:{raw_title}", i, score) for i, (work_id, score) in enumerate(results, 1)])
                        diagnostics["candidate_counts"][f"reference:{raw_title}"] = len(results)
                    except Exception as error:
                        info.update(status="failed", error=str(error))
                        log.warning("Reference resolution failed for %s: %s", raw_title, error)
                    diagnostics["references"].append(info)

        fused = self.fusion.fuse(ranked_lists)
        diagnostics["candidate_counts"]["after_fusion"] = len(fused)
        ids = [x.work_id for x in fused if x.work_id not in excluded]
        if has_structured:
            allowed = {x.work_id for x in self.structured.filter_candidates(ids, plan.structured_filters)}
            fused = [x for x in fused if x.work_id in allowed and x.work_id not in excluded]
        else:
            fused = [x for x in fused if x.work_id not in excluded]
        diagnostics["candidate_counts"]["after_structured_filter"] = len(fused)
        response = BookSearchResponse(query, plan, self._load_books([x.work_id for x in fused[:max(1, top_k)]], fused), diagnostics if debug else {})
        if debug:
            self._print_candidates(response.results, diagnostics)
        return response

    @staticmethod
    def _print_debug_header(query: str, plan: BookSearchPlan, routing: dict[str, bool]) -> None:
        print("\n========== BOOK SEARCH DEBUG ==========")
        print("\nQUERY\n" + query)
        print("\nLLM SEARCH PLAN (JSON)\n" + json.dumps(plan.model_dump(), indent=2, ensure_ascii=False, default=str))
        print("\nROUTING / TOOLS")
        for name, enabled in routing.items():
            print(f"  {'USE' if enabled else 'SKIP':4} {name}")

    @staticmethod
    def _print_candidates(results: list[dict[str, Any]], diagnostics: dict[str, Any]) -> None:
        print("\nREFERENCE RESOLUTION")
        print(json.dumps(diagnostics.get("references", []), indent=2, ensure_ascii=False, default=str))
        print("\nRETRIEVAL COUNTS")
        print(json.dumps(diagnostics.get("candidate_counts", {}), indent=2, ensure_ascii=False))
        print("\nFINAL CANDIDATES")
        for rank, item in enumerate(results, 1):
            print(f"  {rank:>2}. [{item['work_id']}] {item['title']} | {item.get('first_author') or 'Unknown'} | fusion={item.get('fusion_score', 'n/a')}")

    def _load_books(self, ids: list[int], fused=None) -> list[dict[str, Any]]:
        if not ids:
            return []
        scores = {x.work_id: x for x in (fused or [])}
        rows = {b.work_id: b for b in self.db.query(Book).filter(Book.work_id.in_(ids)).all()}
        output = []
        for work_id in ids:
            book = rows.get(work_id)
            if not book:
                continue
            item = {"work_id": book.work_id, "title": book.title, "first_author": book.first_author,
                    "earliest_known_publication_year": book.earliest_known_publication_year, "description": book.description,
                    "content_tags": json.loads(book.content_tags or "[]"), "series": json.loads(book.series or "[]"),
                    "average_rating": book.average_rating}
            if work_id in scores:
                item["fusion_score"] = scores[work_id].fusion_score
                item["sources"] = scores[work_id].sources
            output.append(item)
        return output
