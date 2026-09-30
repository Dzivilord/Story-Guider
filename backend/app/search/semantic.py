"""Book semantic embedding, FAISS indexing, and retrieval utilities."""
from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data/processed/goodreads_books_processed.parquet"
DEFAULT_ARTIFACT_DIR = ROOT / "data/embeddings"


def _values(value: Any) -> list[str]:
    """Convert JSON/list-like dataset values into readable strings."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        items = list(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                parsed = raw
        items = parsed if isinstance(parsed, (list, tuple)) else [parsed]
    else:
        items = [value]
    result = []
    for item in items:
        if isinstance(item, dict):
            # Series records are commonly {name, position}.
            item = item.get("name", " ".join(str(v) for v in item.values()))
        text = str(item).strip()
        if text and text.lower() not in {"none", "nan"}:
            result.append(text)
    return result


def build_embedding_text(row: dict[str, Any]) -> str:
    parts = []
    for label, key in (("Title", "title"), ("Author", "first_author")):
        value = row.get(key)
        if value is not None and str(value).strip() and str(value).lower() not in {"none", "nan", "unknown"}:
            parts.append(f"{label}: {str(value).strip()}.")
    tags = _values(row.get("content_tags"))
    if tags:
        parts.append(f"Genres: {', '.join(tags)}.")
    series = _values(row.get("series"))
    if series:
        parts.append(f"Series: {', '.join(series)}.")
    description = row.get("description")
    if description is not None and str(description).strip() and str(description).lower() not in {"none", "nan"}:
        parts.append(f"Description: {str(description).strip()}")
    return "\n".join(parts)


class BookEmbeddingService:
    def __init__(self, model_name: str | None = None, batch_size: int | None = None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.batch_size = batch_size or int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
        device = os.getenv("EMBEDDING_DEVICE") or None
        self.model = SentenceTransformer(self.model_name, device=device)

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, batch_size=self.batch_size, show_progress_bar=True, convert_to_numpy=True)
        vectors = np.asarray(vectors, dtype="float32")
        faiss.normalize_L2(vectors)
        return vectors

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_query(self, query: str) -> np.ndarray:
        return self._encode([query])


@dataclass(frozen=True)
class SemanticSearchResult:
    work_id: int
    semantic_score: float


class SemanticBookRetriever:
    def __init__(self, artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR, service: BookEmbeddingService | None = None):
        self.artifact_dir = Path(artifact_dir)
        self.service = service or BookEmbeddingService()
        self.index = faiss.read_index(str(self.artifact_dir / "books.faiss"))
        metadata = json.loads((self.artifact_dir / "metadata.json").read_text(encoding="utf-8"))
        mapping = json.loads((self.artifact_dir / "book_index_mapping.json").read_text(encoding="utf-8"))
        if metadata.get("embedding_model") != self.service.model_name:
            raise ValueError("Embedding model does not match index metadata")
        if metadata.get("embedding_dimension") != self.service.dimension or self.index.d != self.service.dimension:
            raise ValueError("Embedding dimension does not match the FAISS index")
        if not metadata.get("normalized") or metadata.get("faiss_index_type") != "IndexFlatIP":
            raise ValueError("Incompatible index normalization or FAISS type")
        if self.index.ntotal != len(mapping) or metadata.get("book_count") != len(mapping):
            raise ValueError("FAISS vector count and mapping count differ")
        self.mapping = [int(x) for x in mapping]

    def search(self, query: str, top_k: int = 20) -> list[SemanticSearchResult]:
        if not query or top_k <= 0:
            return []
        scores, positions = self.index.search(self.service.encode_query(query), min(top_k, self.index.ntotal))
        return [SemanticSearchResult(self.mapping[pos], float(score)) for score, pos in zip(scores[0], positions[0]) if pos >= 0]


def build_index(dataset: str | Path = DEFAULT_DATASET, artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    dataset, artifact_dir = Path(dataset), Path(artifact_dir)
    df = pd.read_parquet(dataset, columns=["work_id", "title", "first_author", "content_tags", "series", "description"])
    texts = [build_embedding_text(row) for row in df.to_dict("records")]
    if any(not text for text in texts):
        raise ValueError("Every book must produce non-empty embedding text")
    service = BookEmbeddingService()
    embeddings = service.encode_documents(texts)
    index = faiss.IndexFlatIP(service.dimension)
    index.add(embeddings)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(artifact_dir / "books.faiss"))
    mapping = [int(x) for x in df["work_id"].tolist()]
    (artifact_dir / "book_index_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    metadata = {"artifact_version": 1, "embedding_model": service.model_name, "embedding_dimension": service.dimension, "normalized": True, "faiss_index_type": "IndexFlatIP", "book_count": len(mapping)}
    (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
