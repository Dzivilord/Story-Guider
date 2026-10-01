import sys, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.bookguide.agent import BookGuide
CASES=[('SEARCH','Find fantasy books published after 2015.'),('SEARCH','Show me books similar to The Hobbit.'),('SEARCH','I want mystery novels with a female protagonist and a dark atmosphere.'),('SEARCH','Find highly rated science fiction books under 400 pages.'),('SEARCH','Give me books like Dune but with more political intrigue.'),('SEARCH','Find books by Agatha Christie published before 1970.'),('SEARCH','I want something about artificial intelligence and human consciousness.'),('CONTENT_BASED','Recommend something I would probably enjoy based on what I have read before.'),('CONTENT_BASED','What should I read next based on my reading history?'),('CONTENT_BASED','Recommend books that match my usual taste.'),('CONTENT_BASED','Give me something similar to the kinds of books I usually read.'),('CONTENT_BASED','Recommend something for me, but avoid genres and authors I usually dislike.'),('CONTENT_BASED','Based on the books I have read and liked, suggest something new.'),('HYBRID','Find science fiction books after 2015 that fit my usual taste.'),('HYBRID','Give me books similar to Dune, but prioritize ones that match what I normally enjoy.'),('HYBRID','Find mystery novels like Gone Girl that I would personally be likely to enjoy.'),('HYBRID','I want fantasy books with dragons, but rank them according to my reading preferences.'),('HYBRID','Find books about space exploration, but avoid authors and genres I have disliked before.'),('HYBRID','Recommend historical fiction published after 2010 based on the books I have previously enjoyed.'),('HYBRID',"Give me something like The Name of the Wind, but don't show books I've already followed and favor genres and authors I tend to like.")]
parser=argparse.ArgumentParser(); parser.add_argument('--case',type=int); parser.add_argument('--query'); args=parser.parse_args()
if args.case is not None:
    if args.case<1 or args.case>len(CASES): parser.error(f'case must be between 1 and {len(CASES)}')
    expected,q=CASES[args.case-1]; print(f'Running case {args.case}: {q}')
    p=BookGuide().plan(q); print(p.model_dump_json(indent=2)); raise SystemExit(0 if p.mode==expected else 1)
if args.query:
    print(BookGuide().plan(args.query).model_dump_json(indent=2)); raise SystemExit(0)
a=BookGuide(); passed=0
for n,(expected,q) in enumerate(CASES,1):
 p=a.plan(q); ok=p.mode==expected; passed+=ok; print(f'{n:02d} {"PASS" if ok else "FAIL"} expected={expected} actual={p.mode} tools={p.tools_required}')
print(f'Passed {passed}/{len(CASES)}'); raise SystemExit(0 if passed==len(CASES) else 1)
