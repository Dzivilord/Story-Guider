"""Add 20 additional demo users without modifying existing demo profiles."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import User, Book, Interaction

db = SessionLocal()
book_ids = [row[0] for row in db.query(Book.work_id).limit(1000).all()]

for number in range(11, 31):
    user_id = f"DEMO{number:02d}"
    if db.get(User, user_id) is None:
        db.add(User(id=user_id, name=f"Demo Reader {number}"))

db.flush()
for number in range(11, 31):
    user_id = f"DEMO{number:02d}"
    for work_id in random.sample(book_ids, min(12, len(book_ids))):
        item = db.get(Interaction, (user_id, work_id)) or Interaction(user_id=user_id, work_id=work_id)
        signal = random.choice(["liked", "disliked", "followed", "rating"])
        setattr(item, signal, random.randint(1, 5) if signal == "rating" else True)
        db.add(item)

db.commit()
db.close()
print("Created/updated demo users DEMO11 through DEMO30 with random interactions.")
