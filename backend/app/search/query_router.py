import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError
from .model_provider import ModelProvider, provider_from_config
from .router_prompt import SYSTEM_PROMPT
from .schemas import BookSearchPlan

class BookSearchRouter:
    def __init__(self, provider: ModelProvider | None = None, provider_name: str | None = None, model: str | None = None):
        self.provider=provider or provider_from_config(provider_name, model)

    def _trace(self, event: str, **data):
        path=Path(__file__).resolve().parents[3] / 'backend' / 'search_evaluation' / 'logs' / 'router_trace.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        record={'timestamp':datetime.now(timezone.utc).isoformat(),'event':event,**data}
        with path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')

    def route(self, query: str) -> BookSearchPlan:
        if not query or not query.strip(): raise ValueError('Book query cannot be empty')
        schema=BookSearchPlan.model_json_schema()
        prompt=query.strip()
        last_error=None
        for attempt in range(1):
            self._trace('request',query=query.strip(),attempt=attempt+1,provider=self.provider.__class__.__name__,user_prompt=prompt,schema=schema)
            try:
                raw=self.provider.complete_structured(SYSTEM_PROMPT,prompt,schema)
            except Exception as error:
                self._trace('provider_error',query=query.strip(),attempt=attempt+1,error_type=type(error).__name__,error=str(error))
                raise
            self._trace('raw_output',query=query.strip(),attempt=attempt+1,raw_output=raw)
            try: return BookSearchPlan.model_validate(raw)
            except ValidationError as error:
                last_error=error
                self._trace('validation_error',query=query.strip(),attempt=attempt+1,raw_output=raw,validation_errors=error.errors(),canonical_schema=schema)
                prompt=f'''The previous BookSearchPlan was structurally valid but failed logical validation.
User query: {query.strip()}
Validation error: {error}
Return the same canonical BookSearchPlan schema again. Salvage every valid component independently. Move only the invalid or unsupported part into semantic_query, preserving valid structured_filters, reference_books, and ranking_preferences. Make retrieval_mode consistent with the components that remain. Use full semantic fallback only when no component can be represented safely.'''
        self._trace('route_failed',query=query.strip(),error=str(last_error),canonical_schema=schema)
        raise ValueError(f'BookSearchPlan validation failed after retry: {last_error}') from last_error
