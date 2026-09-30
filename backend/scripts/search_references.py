import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.search.references import ReferenceBookResolver

parser = argparse.ArgumentParser(description="Resolve reference books locally/external and search FAISS candidates")
parser.add_argument("titles", nargs="+", help="one or more reference titles")
parser.add_argument("--top-k", type=int, default=10)
args = parser.parse_args()
db = SessionLocal()
try:
    resolver = ReferenceBookResolver(db)
    references = []
    for title in args.titles:
        while True:
            try:
                references.append(resolver.resolve(title))
                break
            except ValueError as exc:
                if str(exc).startswith("AMBIGUOUS_REFERENCE_AUTHOR_REQUIRED") or str(exc).startswith("Author does not match"):
                    author = input(f"Nhập author của '{title}': ")
                    try:
                        references.append(resolver.resolve(title, author)); break
                    except ValueError as retry_error:
                        print(retry_error)
                else:
                    raise
    print("References:")
    for reference in references:
        print(f"- {reference.title} | {reference.author or ''} | source={reference.source} | work_id={reference.work_id or ''}")
    print("Candidates:")
    for rank, (work_id, score) in enumerate(resolver.search_candidates(references, args.top_k), 1):
        print(f"{rank}\t{work_id}\t{score:.4f}")
finally:
    db.close()
