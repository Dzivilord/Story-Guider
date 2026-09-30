import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data/app/recsys.db').as_posix()}")
GENRES = ["Fantasy", "Science Fiction", "Mystery", "Thriller", "Romance", "Horror", "Historical Fiction", "History", "Biography", "Young Adult", "Children", "Classics", "Nonfiction", "Contemporary", "Adventure"]
