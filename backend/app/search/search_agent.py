import json
from .agent_schemas import SearchAction, SearchAgentState, CompactObservation
from .agent_prompt import AGENT_PROMPT
from .query_router import BookSearchRouter
from .candidate_store import CandidateStore
from .tools import SearchTools

class SearchAgent:
    def __init__(self,db,provider=None,max_iterations=6):
        self.db=db; self.provider=provider; self.max_iterations=max_iterations; self.last_state=None
    def _decide(self,state):
        context={'user_query':state.user_query,'plan':state.plan.model_dump(),'candidate_set_id':state.current_candidate_set_id,'candidate_count':state.candidate_count,'recent_observations':[x.model_dump() for x in state.observations[-3:]]}
        raw=self.provider.complete_structured(AGENT_PROMPT,json.dumps(context),SearchAction.model_json_schema()); return SearchAction.model_validate(raw)
    def _complete_arguments(self, action, arguments, plan, observations=None):
        """Supply plan-derived inputs when the agent selects a tool without args."""
        args=dict(arguments)
        if action=='SEARCH_METADATA':
            args={**plan.structured_filters.model_dump(), 'ranking_preferences':[x.model_dump() for x in plan.ranking_preferences], **args}
        elif action=='SEMANTIC_SEARCH' and not args.get('query') and not args.get('semantic_query'):
            args['query']=plan.semantic_query
        elif action=='SEMANTIC_REFERENCE_SEARCH' and not args.get('reference_books'):
            args['reference_books']=plan.reference_books
        elif action=='COMBINE_CANDIDATES':
            if not args.get('candidate_set_ids') and observations:
                ids=[]
                for observation in observations:
                    if observation.candidate_set_id and observation.candidate_set_id not in ids:
                        ids.append(observation.candidate_set_id)
                args['candidate_set_ids']=ids[-2:]
            args.setdefault('strategy','union')
        return args
    def run(self,user_query):
        plan=BookSearchRouter(provider=self.provider).route(user_query); state=SearchAgentState(user_query=user_query,plan=plan); self.last_state=state; tools=SearchTools(self.db,CandidateStore()); seen=set()
        for i in range(self.max_iterations):
            state.iteration=i+1; action=self._decide(state); action.arguments=self._complete_arguments(action.action,action.arguments,state.plan,state.observations); key=(action.action,json.dumps(action.arguments,sort_keys=True))
            if key in seen: state.status='FAILED'; state.observations.append(CompactObservation(status='error',message='NO_PROGRESS')); raise RuntimeError('Search agent made no progress')
            seen.add(key); state.executed_actions.append(action)
            if action.action=='FINISH':
                cid=action.arguments.get('candidate_set_id') or state.current_candidate_set_id
                if not cid: raise RuntimeError('FINISH requires candidate_set_id')
                state.status='DONE'; return state,cid,tools.store.get(cid)
            observation=tools.execute(action.action,action.arguments); state.observations.append(observation)
            if observation.candidate_set_id: state.current_candidate_set_id=observation.candidate_set_id; state.candidate_count=observation.candidate_count or 0
            if observation.status=='error': state.status='FAILED'; raise RuntimeError(observation.message)
        state.status='FAILED'; raise RuntimeError('Search agent exceeded maximum iterations')
