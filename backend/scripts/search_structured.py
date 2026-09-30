import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.search.schemas import BookFilters
from app.search.structured import StructuredBookRetriever

parser = argparse.ArgumentParser()
parser.add_argument('--title'); parser.add_argument('--author', action='append', default=[])
parser.add_argument('--genre', action='append', default=[]); parser.add_argument('--series', action='append', default=[])
parser.add_argument('--year-min', type=int); parser.add_argument('--year-max', type=int)
parser.add_argument('--rating-min', type=float); parser.add_argument('--rating-max', type=float)
parser.add_argument('--length', action='append', default=[]); parser.add_argument('--language', action='append', default=[])
parser.add_argument('--limit', type=int, default=20); args = parser.parse_args()
filters = BookFilters(title=args.title, authors=args.author, genres=args.genre, publication_year_min=args.year_min, publication_year_max=args.year_max, rating_min=args.rating_min, rating_max=args.rating_max, length_categories=args.length, languages=args.language, series=args.series)
db = SessionLocal()
try:
    for i, row in enumerate(StructuredBookRetriever(db).search(filters, args.limit), 1):
        print(f'{i}\t{row.work_id}\t{row.title}\t{row.author or ""}\t{row.publication_year or ""}\t{row.average_rating or ""}')
finally:
    db.close()
