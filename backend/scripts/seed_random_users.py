"""Create demo users and random unified interaction rows."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import User, Book, Interaction

db=SessionLocal(); books=db.query(Book.work_id).limit(1000).all(); ids=[x[0] for x in books]
for n in range(1, 11):
    uid=f'DEMO{n:02d}'; user=db.get(User,uid)
    if not user: db.add(User(id=uid,name=f'Demo Reader {n}'))
db.flush()
for n in range(1, 11):
    uid=f'DEMO{n:02d}'
    for work_id in random.sample(ids, min(12,len(ids))):
        item=db.get(Interaction,(uid,work_id)) or Interaction(user_id=uid,work_id=work_id)
        signal=random.choice(['liked','disliked','followed','rating'])
        setattr(item, signal, random.randint(1,5) if signal=='rating' else True); db.add(item)
db.commit(); db.close(); print('Created/updated 10 demo users with random interactions.')
