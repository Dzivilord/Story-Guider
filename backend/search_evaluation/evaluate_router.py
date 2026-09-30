import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.search.query_router import BookSearchRouter
from routing_cases import CASES

def main():
    p=argparse.ArgumentParser(); p.add_argument('--provider',choices=['api','gemini','ollama']); p.add_argument('--model'); p.add_argument('--query'); a=p.parse_args()
    router=BookSearchRouter(provider_name=a.provider,model=a.model)
    if a.query:
        print(router.route(a.query).model_dump_json(indent=2)); return
    passed=0
    for i,case in enumerate(CASES,1):
        try: plan=router.route(case['query']); ok=plan.retrieval_mode==case['expected_mode']; passed+=ok
        except Exception as exc: plan=None; ok=False; print(f'[{i:02d}] ERROR: {exc}')
        print(f'[{i:02d}] {case["query"]}\nExpected: {case["expected_mode"]} | Predicted: {plan.retrieval_mode if plan else "ERROR"} | {"PASS" if ok else "FAIL"}')
        if plan: print(plan.model_dump_json(indent=2))
        print('-'*60)
    print(f'Routing accuracy: {passed} / {len(CASES)} = {passed/len(CASES):.1%}')
if __name__=='__main__': main()
