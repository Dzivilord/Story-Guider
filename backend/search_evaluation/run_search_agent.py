import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.search.model_provider import provider_from_config
from app.search.search_agent import SearchAgent

p=argparse.ArgumentParser(); p.add_argument('--provider',choices=['api','gemini','ollama']); p.add_argument('--model'); p.add_argument('--query',default='Books like Dune but shorter'); a=p.parse_args()
provider=provider_from_config(a.provider,a.model); db=SessionLocal(); agent=SearchAgent(db,provider); state=None
try:
    state,candidate_id,candidates=agent.run(a.query)
    books=db.query(__import__('app.models',fromlist=['Book']).Book).filter(__import__('app.models',fromlist=['Book']).Book.work_id.in_(candidates.book_ids)).all()
except Exception as exc:
    state=agent.last_state; print(f'Agent failed: {exc}')
finally: db.close()
if state:
    print(f'Query: {state.user_query}')
    print(f'Plan: {state.plan.model_dump_json(indent=2)}')
    print(f'Status: {state.status}, iterations: {state.iteration}')
    for i,action in enumerate(state.executed_actions,1):
        print(f'Iteration {i}: ACTION {action.action} args={action.arguments} reasoning={action.reasoning_summary}')
        if i<=len(state.observations): print(f'Iteration {i}: OBSERVATION {state.observations[i-1].model_dump_json()}')
    if 'candidate_id' in locals():
        print(f'Candidate set: {candidate_id}, count: {len(candidates.book_ids)}')
        print('Rank\twork_id\ttitle\tauthor\tyear\trating')
        by_id={b.work_id:b for b in books}
        for rank,work_id in enumerate(candidates.book_ids,1):
            book=by_id.get(work_id)
            if book: print(f'{rank}\t{book.work_id}\t{book.title}\t{book.first_author or ""}\t{book.earliest_known_publication_year or ""}\t{book.average_rating or ""}')
