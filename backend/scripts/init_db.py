import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import Base, engine
Base.metadata.create_all(engine)
print('SQLite database initialized')
