from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import func
from ..models import Book
from .semantic import SemanticBookRetriever, build_embedding_text


def normalize_title(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def author_similarity(left: str | None, right: str | None) -> float:
    return SequenceMatcher(None, normalize_title(left or ""), normalize_title(right or "")).ratio()


@dataclass
class ReferenceBook:
    title: str
    author: str | None
    description: str | None
    genres: list[str]
    source: str
    work_id: int | None = None

    def embedding_text(self) -> str:
        return build_embedding_text({"title": self.title, "first_author": self.author, "description": self.description, "content_tags": self.genres, "series": []})


class ReferenceBookResolver:
    def __init__(self, db, retriever: SemanticBookRetriever | None = None):
        self.db = db
        self.retriever = retriever or SemanticBookRetriever()

    def local_matches(self, title: str, limit: int = 10) -> list[Book]:
        needle = normalize_title(title)
        if not needle:
            return []

        # A reference title is an entity lookup, not a semantic search.  Using
        # only the first token (for example ``my``) and then fuzzy matching
        # makes unrelated titles such as "My Secret Admirer" match
        # "My Sweet Orange Tree".  Fetch candidates by that token for
        # efficiency, but accept only titles that are an exact match or whose
        # full normalized title starts with the user's phrase.  This preserves
        # useful partial lookups: "my" and "my secret" both resolve to
        # "My Secret Admirer", while "my sweet orange tree" does not.
        prefix = needle.split()[0]
        books = self.db.query(Book).filter(func.lower(Book.title).like(f"%{prefix}%")).limit(500).all()
        ranked = []
        for book in books:
            candidate = normalize_title(book.title)
            if candidate == needle:
                ranked.append((2.0, book))
            elif candidate.startswith(f"{needle} "):
                ranked.append((1.0 + len(needle) / max(len(candidate), 1), book))
        return [book for _, book in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]

    def resolve(self, title: str, author: str | None = None) -> ReferenceBook:
        matches = self.local_matches(title)
        if matches:
            if len(matches) > 1 and author:
                matches.sort(key=lambda book: author_similarity(book.first_author, author), reverse=True)
                if author_similarity(matches[0].first_author, author) < 0.65:
                    raise ValueError(f"Author does not match local reference candidates for '{title}'")
            elif len(matches) > 1:
                raise ValueError(f"AMBIGUOUS_REFERENCE_AUTHOR_REQUIRED:{title}")
            book = matches[0]
            try: genres = json.loads(book.content_tags or "[]")
            except json.JSONDecodeError: genres = []
            return ReferenceBook(book.title, book.first_author, book.description, genres, "sqlite", book.work_id)
        return self._external_lookup(title, author)

    def _external_lookup(self, title: str, author: str | None) -> ReferenceBook:
        query = title if not author else f"{title} {author}"
        url = "https://openlibrary.org/search.json?limit=5&q=" + urllib.parse.quote(query)
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read())
        docs = payload.get("docs", [])
        if not docs: raise ValueError(f"REFERENCE_NOT_FOUND:{title}")
        if author:
            docs.sort(key=lambda doc: author_similarity((doc.get("author_name") or [None])[0], author), reverse=True)
        doc = docs[0]
        return ReferenceBook(doc.get("title") or title, (doc.get("author_name") or [author])[0], doc.get("first_sentence"), doc.get("subject", [])[:12], "openlibrary")

    def search_candidates(self, references: list[ReferenceBook], top_k_each: int = 20) -> list[tuple[int, float]]:
        result: list[tuple[int, float]] = []
        seen: set[int] = set()
        for reference in references:
            vector = self.retriever.service.encode_query(reference.embedding_text())
            scores, positions = self.retriever.index.search(vector, top_k_each)
            for score, position in zip(scores[0], positions[0]):
                if position >= 0 and self.retriever.mapping[position] not in seen:
                    work_id = self.retriever.mapping[position]; seen.add(work_id); result.append((work_id, float(score)))
        return result
