"""Run one BookGuide case with a step-by-step execution trace."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.bookguide.agent import BookGuide
from bookguide_cases import CASES

parser=argparse.ArgumentParser()
parser.add_argument('--case', type=int)
parser.add_argument('--query')
parser.add_argument('--user-id', '--user', dest='user_id', default='DEMO01')
parser.add_argument('--top-k', '--top', dest='top_k', type=int, default=10)
args=parser.parse_args()
if args.case is None and not args.query:
    parser.error('Use --case 1..20 or --query "..."')
if args.case:
    if args.case<1 or args.case>len(CASES): parser.error(f'case must be between 1 and {len(CASES)}')
    expected,query=CASES[args.case-1]
else: expected,query='custom',args.query
print(f'CASE: {args.case or "custom"}\nEXPECTED: {expected}\nQUERY: {query}\nUSER: {args.user_id}')
db=SessionLocal()
try:
    print('\nEXECUTION START')
    response=BookGuide(db).run(args.user_id,query,args.top_k,debug=True)
    print('\nTOOLS USED:',response.tools_used)
    print('RESULT COUNT:',len(response.results))
finally: db.close()
