import json
import os
from pathlib import Path
from abc import ABC, abstractmethod
from urllib.request import Request, urlopen
from urllib.error import HTTPError
PROJECT_ROOT = Path(__file__).resolve().parents[3]
env_file=PROJECT_ROOT / '.env'
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8').splitlines():
        key, separator, value=line.partition('=')
        if separator and key.strip() and not key.lstrip().startswith('#'):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

class ModelProvider(ABC):
    @abstractmethod
    def complete_structured(self, system_prompt: str, user_query: str, schema: dict) -> dict: ...

def _gemini_schema(schema: dict) -> dict:
    """Convert Pydantic JSON Schema to Gemini's supported response schema."""
    definitions = schema.get('$defs', {})

    def convert(node: dict) -> dict:
        if '$ref' in node:
            target = definitions
            for part in node['$ref'].removeprefix('#/$defs/').split('/'):
                target = target[part]
            return convert(target)

        # Pydantic represents Optional[T] as anyOf([T, null]). Gemini uses
        # nullable instead of JSON Schema's anyOf for this case.
        if 'anyOf' in node:
            non_null = [item for item in node['anyOf'] if item.get('type') != 'null']
            if len(non_null) == 1 and len(non_null) != len(node['anyOf']):
                result = convert(non_null[0])
                result['nullable'] = True
                return result

        result = {}
        for key in ('type', 'enum', 'format', 'nullable'):
            if key in node:
                result[key] = node[key]
        if 'properties' in node:
            result['properties'] = {
                name: convert(value) for name, value in node['properties'].items()
            }
        if 'required' in node:
            result['required'] = node['required']
        if 'items' in node:
            result['items'] = convert(node['items'])
        return result

    return convert(schema)

class ApiModelProvider(ModelProvider):
    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None):
        self.model=model or os.getenv('LLM_MODEL','gpt-4o-mini'); self.api_key=api_key or os.getenv('OPENAI_API_KEY')
        self.base_url=(base_url or os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1')).rstrip('/')
    def complete_structured(self, system_prompt, user_query, schema):
        if not self.api_key: raise RuntimeError('OPENAI_API_KEY is required for the API provider')
        body=json.dumps({'model':self.model,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':user_query}],'response_format':{'type':'json_schema','json_schema':{'name':'book_search_plan','strict':True,'schema':schema}}}).encode()
        req=Request(self.base_url+'/chat/completions',data=body,headers={'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json'})
        with urlopen(req,timeout=90) as response: payload=json.loads(response.read())
        return json.loads(payload['choices'][0]['message']['content'])

class GeminiModelProvider(ModelProvider):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model=model or os.getenv('LLM_MODEL','gemini-2.0-flash')
        self.api_key=api_key or os.getenv('GEMINI_API_KEY')
    def complete_structured(self, system_prompt, user_query, schema):
        if not self.api_key: raise RuntimeError('GEMINI_API_KEY is required for the Gemini provider')
        body=json.dumps({'system_instruction':{'parts':[{'text':system_prompt}]},'contents':[{'role':'user','parts':[{'text':user_query}]}],'generationConfig':{'responseMimeType':'application/json','responseSchema':_gemini_schema(schema)}}).encode()
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}'
        req=Request(url,data=body,headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=90) as response:
                payload=json.loads(response.read())
        except HTTPError as error:
            detail=error.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'Gemini API returned HTTP {error.code}: {detail}') from error
        return json.loads(payload['candidates'][0]['content']['parts'][0]['text'])

class OllamaModelProvider(ModelProvider):
    def __init__(self, model: str | None = None, base_url: str | None = None): self.model=model or os.getenv('OLLAMA_MODEL','llama3.1:8b'); self.base_url=(base_url or os.getenv('OLLAMA_BASE_URL','http://localhost:11434')).rstrip('/')
    def complete_structured(self, system_prompt, user_query, schema):
        body=json.dumps({'model':self.model,'stream':False,'think':False,'format':schema,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':user_query}]}).encode()
        req=Request(self.base_url+'/api/chat',data=body,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=180) as response: return json.loads(json.loads(response.read())['message']['content'])

def provider_from_config(provider: str | None = None, model: str | None = None) -> ModelProvider:
    selected=(provider or os.getenv('LLM_PROVIDER','api')).lower()
    if selected == 'ollama': return OllamaModelProvider(model)
    if selected == 'gemini': return GeminiModelProvider(model)
    if selected == 'gemini' or (selected == 'api' and (model or os.getenv('LLM_MODEL','')).lower().startswith('gemini')):
        return GeminiModelProvider(model)
    if selected == 'api': return ApiModelProvider(model)
    raise ValueError(f'Unsupported LLM provider: {selected}')
