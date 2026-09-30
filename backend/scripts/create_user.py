import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.main import create_user,UserIn
from app.database import SessionLocal
p=argparse.ArgumentParser(); p.add_argument('--name',required=True); a=p.parse_args()
r=create_user(UserIn(name=a.name),SessionLocal())
print(f"Created user: {r['id']}\nName: {r['name']}")
