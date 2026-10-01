"""Simulate realistic user-book interactions for the demo users."""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import User, Book, Interaction

random.seed(42)
db=SessionLocal()
users=db.query(User).filter(User.id.like('DEMO%')).order_by(User.id).all()
book_ids=[row[0] for row in db.query(Book.work_id).limit(2000).all()]
if not users or not book_ids:
    raise SystemExit('Need demo users and imported books first.')

created=0
for user in users:
    for work_id in random.sample(book_ids, min(20, len(book_ids))):
        item=db.get(Interaction,(user.id,work_id))
        if item is None:
            item=Interaction(user_id=user.id,work_id=work_id); created+=1
        # Independent signals: a book can be liked, followed and rated together.
        profile=random.random()
        if profile < .50:
            item.liked=True
            item.rating=random.choice([4,4,5,5])
            item.followed=random.random()<.45
        elif profile < .72:
            item.followed=True
            if random.random()<.65: item.rating=random.choice([3,4,5])
        elif profile < .90:
            item.disliked=True
            if random.random()<.55: item.rating=random.choice([1,2])
        else:
            item.rating=random.choice([1,2,3,4,5])
        db.add(item)
db.commit()
print(f'Simulated {created} new interaction rows for {len(users)} demo users.')
db.close()
