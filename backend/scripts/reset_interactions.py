"""Recreate the unified interactions table. Existing interaction data is removed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Base, engine
from app.models import Interaction

Interaction.__table__.drop(engine, checkfirst=True)
with engine.begin() as connection:
    connection.exec_driver_sql('DROP TABLE IF EXISTS user_ratings')
    connection.exec_driver_sql('DROP TABLE IF EXISTS user_favorite_genres')
Base.metadata.create_all(engine)
print('Unified interactions table created: liked, disliked, followed, rating')
