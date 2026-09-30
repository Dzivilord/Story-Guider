import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.search.query_router import BookSearchRouter
p=argparse.ArgumentParser(); p.add_argument('--provider',choices=['api','gemini','ollama']); p.add_argument('--model'); a=p.parse_args(); router=BookSearchRouter(provider_name=a.provider,model=a.model)
while True:
    try: query=input('Enter book request (or q to quit): ').strip()
    except EOFError: break
    if query.lower() in {'q','quit','exit'}: break
    try: print(router.route(query).model_dump_json(indent=2))
    except Exception as exc: print(f'Error: {exc}')
