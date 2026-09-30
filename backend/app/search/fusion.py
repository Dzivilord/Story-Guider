"""Ranked candidate fusion utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RankedCandidate:
    work_id: int
    source: str
    rank: int
    similarity: float | None = None


@dataclass
class FusedCandidate:
    work_id: int
    fusion_score: float
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)


class CandidateFusionService:
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = max(1, int(rrf_k))

    def fuse(self, ranked_lists: list[list[RankedCandidate]]) -> list[FusedCandidate]:
        merged: dict[int, FusedCandidate] = {}
        for ranked_list in ranked_lists:
            for item in ranked_list:
                contribution = 1.0 / (self.rrf_k + item.rank)
                candidate = merged.setdefault(item.work_id, FusedCandidate(item.work_id, 0.0))
                candidate.fusion_score += contribution
                provenance = {"rank": item.rank, "rrf_contribution": contribution}
                if item.similarity is not None:
                    provenance["similarity"] = item.similarity
                candidate.sources[item.source] = provenance
        return sorted(merged.values(), key=lambda x: (-x.fusion_score, x.work_id))
