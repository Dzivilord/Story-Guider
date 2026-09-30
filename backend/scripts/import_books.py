import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from app.database import SessionLocal
from app.models import Book
root = Path(__file__).resolve().parents[2]
source = root / 'data/processed/goodreads_books_processed.parquet'
columns = ['work_id','title','description','first_author','content_tags','series','earliest_known_publication_year','publication_decade','pages','length_category','average_rating','ratings_count','reviews_count','has_rating','rating_confidence','weighted_rating','log_ratings_count','log_reviews_count','num_editions','log_num_editions','is_part_of_series','url','language']
def scalar(value):
    if value is None: return None
    if not isinstance(value, (list, tuple, np.ndarray)):
        try:
            if pd.isna(value): return None
        except (TypeError, ValueError): pass
    if isinstance(value, np.generic): return value.item()
    return value
def json_array(value):
    value = scalar(value)
    if value is None: return '[]'
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list): return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError: pass
        return json.dumps([value], ensure_ascii=False)
    if isinstance(value, (list, tuple, np.ndarray)): return json.dumps([scalar(x) for x in value], ensure_ascii=False)
    return '[]'
integer_fields = {'work_id','earliest_known_publication_year','pages','ratings_count','reviews_count','num_editions'}
boolean_fields = {'has_rating','is_part_of_series'}
df = pd.read_parquet(source, columns=columns)
db = SessionLocal(); inserted = updated = failed = 0; first_error = None
for row in df.to_dict('records'):
    try:
        values = {key: scalar(value) for key, value in row.items()}
        for key in ('content_tags','series'): values[key] = json_array(row[key])
        for key in integer_fields:
            if values[key] is not None: values[key] = int(values[key])
        for key in boolean_fields:
            if values[key] is not None: values[key] = bool(values[key])
        book = db.get(Book, values['work_id'])
        if book:
            for key, value in values.items(): setattr(book, key, value)
            updated += 1
        else:
            db.add(Book(**values)); inserted += 1
    except Exception as exc:
        failed += 1
        if first_error is None: first_error = repr(exc)
db.commit(); db.close()
print(f'Read: {len(df)}; inserted: {inserted}; updated: {updated}; failed: {failed}')
if first_error: print(f'First failure: {first_error}')
