"""HeardIt's public, privacy-preserving listening experiment API."""
import hashlib, json, secrets, uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from gridfs import AsyncGridFSBucket

from app.core.config import get_settings
from app.core.errors import AppError
from app.db import require_database
from app.services.fish_tts import is_audio

router = APIRouter()
settings = get_settings()
now = lambda: datetime.now(timezone.utc).isoformat()

class SuggestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sentence: str = Field(min_length=1, max_length=180)
    intended_label: str | None = Field(default=None, max_length=60)

class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intended_label: str = Field(min_length=2, max_length=60)
    alternative_labels: list[str] = Field(min_length=3, max_length=3)
    fish_direction: str = Field(min_length=2, max_length=120)
    explanation: str = Field(min_length=2, max_length=180)

    @field_validator('alternative_labels')
    @classmethod
    def distinct_labels(cls, labels, info):
        intended = info.data.get('intended_label', '')
        if len({x.strip().casefold() for x in [intended, *labels]}) != 4:
            raise ValueError('All four interpretations must be distinct.')
        return [x.strip() for x in labels]

class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sentence: str = Field(min_length=1, max_length=180)
    direction: str = Field(min_length=1, max_length=120)

class CreateTest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sentence: str = Field(min_length=1, max_length=180)
    intended_label: str = Field(min_length=1, max_length=60)
    distractors: list[str] = Field(min_length=3, max_length=3)
    direction: str = Field(min_length=1, max_length=120)
    audio_id: str = Field(min_length=1)
    option_descriptions: list[str] = Field(default_factory=list, max_length=4)

    @field_validator('distractors')
    @classmethod
    def four_distinct(cls, labels, info):
        all_labels = [info.data.get('intended_label', ''), *labels]
        if len({x.strip().casefold() for x in all_labels}) != 4:
            raise ValueError('The intended label and three alternatives must be distinct.')
        return [x.strip() for x in labels]

    @field_validator('option_descriptions')
    @classmethod
    def descriptions_match_options(cls, descriptions):
        if descriptions and len(descriptions) != 4:
            raise ValueError('Provide either zero or four option descriptions.')
        return [value.strip()[:120] for value in descriptions]

class VoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participant_id: str = Field(min_length=24, max_length=128)
    selected_option_id: str | None = Field(default=None, min_length=1, max_length=64)
    selected_label: str | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode='after')
    def one_selection(self):
        if bool(self.selected_option_id) == bool(self.selected_label):
            raise ValueError('Choose exactly one answer option.')
        return self

def _db(db):
    return db

def _gridfs(db):
    return AsyncGridFSBucket(db, bucket_name='heardit_audio')

def _cache_key(sentence, direction):
    normalized_sentence = ' '.join(sentence.split())
    normalized_direction = ' '.join(direction.split())
    payload = {'model': settings.fish_tts_model, 'text': f'{normalized_direction} {normalized_sentence}', 'direction': normalized_direction, 'voice': 'fish-account-default-v1', 'format': 'mp3', 'output': {'sample_rate': 44100}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

@router.get('/health')
async def health(db=Depends(require_database)):
    return {'status': 'ok', 'database': 'mongodb', 'fish_configured': bool(settings.fish_api_key.get_secret_value())}

@router.post('/api/v1/suggestions')
async def suggestions(body: SuggestRequest, request: Request, db=Depends(require_database)):
    if not settings.aiml_api_key.get_secret_value():
        raise AppError(503, 'aiml_not_configured', 'AI suggestions are unavailable right now. Add interpretations manually and continue.')
    ip = request.client.host if request.client else 'unknown'
    await _rate_limit(db, 'suggest:' + hashlib.sha256(ip.encode()).hexdigest(), 30)
    schema = Suggestion.model_json_schema()
    headers = {'Authorization': f'Bearer {settings.aiml_api_key.get_secret_value()}'}
    error = None
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(2):
            try:
                response = await client.post('https://api.aimlapi.com/v1/chat/completions', headers=headers, json={'model': settings.aiml_model, 'messages': [{'role': 'system', 'content': 'Suggest four concise, plausible emotional interpretations for a spoken sentence. Return only schema-valid JSON. Never claim to know how audio sounds.'}, {'role': 'user', 'content': f"Sentence: {body.sentence}\nCreator's intended interpretation, if supplied: {body.intended_label or 'not supplied'}"}], 'response_format': {'type': 'json_schema', 'json_schema': {'name': 'heardit_suggestion', 'strict': True, 'schema': schema}}})
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 0: continue
                raise AppError(503, 'aiml_unavailable', 'AI suggestions could not connect. Add interpretations manually and continue.') from exc
            if response.status_code in (402, 429):
                raise AppError(503, 'aiml_credits_unavailable', 'AI suggestions are temporarily unavailable. Add interpretations manually and continue.')
            if response.status_code >= 400:
                raise AppError(502, 'aiml_unavailable', 'AI suggestions failed. Add interpretations manually and continue.')
            try:
                value = response.json()['choices'][0]['message']['content']
                return Suggestion.model_validate_json(value).model_dump()
            except Exception as exc:
                error = exc
    raise AppError(502, 'aiml_invalid_output', 'AI could not suggest valid choices. Add interpretations manually and continue.') from error

@router.post('/api/v1/audio/generate')
async def generate(body: GenerateRequest, request: Request, db=Depends(require_database)):
    key = settings.fish_api_key.get_secret_value()
    if not key: raise AppError(503, 'fish_not_configured', 'Fish Audio is not configured on the API server.')
    ip = request.client.host if request.client else 'unknown'
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    await _rate_limit(db, 'generate:' + ip_hash, 10)
    cache = _cache_key(body.sentence, body.direction)
    cached = await db.audio_assets.find_one({'cache_key': cache})
    if cached: return {'audio_id': cached['id'], 'url': f"/api/v1/audio/{cached['id']}", 'cached': True, 'model': cached['model'], 'direction': cached['direction'], 'voice': cached['voice'], 'created_at': cached['created_at']}
    full_text = f'{body.direction.strip()} {body.sentence.strip()}'
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post('https://api.fish.audio/v1/tts', headers={'Authorization': f'Bearer {key}', 'model': settings.fish_tts_model}, json={'text': full_text, 'format': 'mp3'})
    except httpx.TimeoutException as e: raise AppError(503, 'fish_timeout', 'Fish Audio took too long. Try again.') from e
    except httpx.NetworkError as e: raise AppError(503, 'fish_unavailable', 'Fish Audio could not be reached. Try again shortly.') from e
    if res.status_code in (401, 403): raise AppError(502, 'fish_authentication_failed', 'Fish Audio rejected the configured key.')
    if res.status_code == 402: raise AppError(503, 'fish_quota_unavailable', 'Fish Audio reports that account quota is unavailable.')
    if res.status_code == 429: raise AppError(429, 'fish_rate_limited', 'Fish Audio is rate limiting requests. Try again shortly.')
    if res.status_code >= 400: raise AppError(502, 'fish_unavailable', 'Fish Audio could not generate this clip.')
    audio = res.content
    # Vercel Functions cap the complete response payload at 4.5 MB. Keep a little
    # headroom so serving a stored MP3 remains reliable on the intended platform.
    if res.headers.get('content-type','').split(';')[0] not in ('audio/mpeg','audio/mp3','application/octet-stream') or not is_audio(audio) or len(audio) > 4_000_000:
        raise AppError(502, 'fish_invalid_audio', 'Fish Audio returned an invalid MP3.')
    audio_id = str(uuid.uuid4())
    created_at = now()
    try:
        grid_id = await _gridfs(db).upload_from_stream(audio_id, audio, metadata={'contentType':'audio/mpeg','cache_key':cache})
        await db.audio_assets.insert_one({'id':audio_id,'gridfs_id':grid_id,'cache_key':cache,'content_type':'audio/mpeg','storage_reference':str(grid_id),'file_size':len(audio),'model':settings.fish_tts_model,'direction':body.direction,'voice':'fish-account-default-v1','input_text':full_text,'created_at':created_at})
    except Exception as exc:
        raise AppError(503, 'audio_storage_failed', 'The generated clip could not be saved. It is not ready to publish.') from exc
    return {'audio_id':audio_id,'url':f'/api/v1/audio/{audio_id}','cached':False,'model':settings.fish_tts_model,'direction':body.direction,'voice':'fish-account-default-v1','created_at':created_at}

async def _rate_limit(db, key, max_count, seconds=3600):
    from datetime import timedelta
    window = int(datetime.now(timezone.utc).timestamp()) // seconds
    result = await db.heardit_rate_limits.find_one_and_update({'_id':f'{key}:{window}'},{'$inc':{'count':1},'$setOnInsert':{'expires_at':datetime.now(timezone.utc)+timedelta(seconds=seconds*2)}},upsert=True,return_document=ReturnDocument.AFTER)
    if result['count'] > max_count: raise AppError(429,'rate_limited','Too many requests. Please try again later.')

@router.post('/api/v1/tests', status_code=201)
async def create_test(body: CreateTest, db=Depends(require_database)):
    asset = await db.audio_assets.find_one({'id':body.audio_id})
    if not asset: raise AppError(422,'audio_required','Generate and save audio before publishing this test.')
    if asset.get('input_text') != f'{body.direction.strip()} {body.sentence.strip()}': raise AppError(422,'audio_mismatch','Generate audio for the current sentence and direction before publishing.')
    test_id, token = secrets.token_urlsafe(12), secrets.token_urlsafe(32)
    labels = [body.intended_label.strip(), *body.distractors]
    descriptions = body.option_descriptions or ['', '', '', '']
    options = [{'id':str(uuid.uuid4()), 'label':label, 'description':description} for label, description in zip(labels, descriptions)]
    doc = {'id':test_id,'sentence':body.sentence,'intended_label':body.intended_label.strip(),'intended_option_id':options[0]['id'],'distractors':body.distractors,'options':options,'direction':body.direction,'model':asset['model'],'audio_id':asset['id'],'creator_management_token_hash':hashlib.sha256(token.encode()).hexdigest(),'status':'published','created_at':now()}
    await db.heardit_tests.insert_one(doc)
    return {'id':test_id,'management_token':token,'status':'published'}

def _require_management_token(test, token):
    expected = test.get('creator_management_token_hash', '')
    supplied = hashlib.sha256((token or '').encode()).hexdigest()
    if not token or not expected or not secrets.compare_digest(supplied, expected):
        raise AppError(401, 'creator_access_required', 'Open this page on the device that created the test, or use its private creator access.')

@router.get('/api/v1/tests/{test_id}/creator')
async def creator_test(test_id: str, x_management_token: str | None = Header(default=None), db=Depends(require_database)):
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    _require_management_token(test, x_management_token)
    return {'id':test['id'],'sentence':test['sentence'],'intended_label':test['intended_label'],'distractors':test['distractors'],'direction':test['direction'],'model':test['model'],'audio_id':test['audio_id'],'created_at':test['created_at'],'status':test['status']}

@router.get('/api/v1/tests/{test_id}/public')
async def public_test(test_id: str, participant_id: str, db=Depends(require_database)):
    doc = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not doc: raise AppError(404,'test_not_found','This listening test could not be found.')
    participant_hash = hashlib.sha256(participant_id.encode()).hexdigest()
    assigned = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':participant_hash})
    if not assigned: raise AppError(422,'assignment_required','Get your listening condition before opening the test.')
    options = doc.get('options') or [{'id':hashlib.sha256(f"{test_id}:{label}".encode()).hexdigest()[:24], 'label':label, 'description':''} for label in [doc['intended_label'],*doc['distractors']]]
    secrets.SystemRandom().shuffle(options)
    result = {'id':doc['id'],'options':options,'labels':[item['label'] for item in options],'condition':assigned['condition']}
    if assigned['condition'] == 'audio': result['audio_url'] = f"/api/v1/audio/{doc['audio_id']}"
    else: result['sentence'] = doc['sentence']
    return result

@router.post('/api/v1/tests/{test_id}/assignment')
async def assignment(test_id: str, body: dict, x_management_token: str | None = Header(default=None), db=Depends(require_database)):
    participant = body.get('participant_id','')
    if not isinstance(participant,str) or not 24 <= len(participant) <= 128: raise AppError(422,'invalid_participant','A stable browser participant ID is required.')
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    if x_management_token and secrets.compare_digest(hashlib.sha256(x_management_token.encode()).hexdigest(), test['creator_management_token_hash']): raise AppError(403,'creator_preview','Creator previews are excluded from listener assignment.')
    hashed = hashlib.sha256(participant.encode()).hexdigest()
    row = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':hashed})
    if not row:
        # Insert-once assignment is stable under concurrent refreshes.
        condition = secrets.choice(['audio','text'])
        try: await db.heardit_assignments.insert_one({'test_id':test_id,'participant_hash':hashed,'condition':condition,'created_at':now()})
        except DuplicateKeyError: pass
        row = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':hashed})
    return {'condition':row['condition']}

@router.post('/api/v1/tests/{test_id}/votes', status_code=201)
async def vote(test_id: str, body: VoteRequest, x_management_token: str | None = Header(default=None), db=Depends(require_database)):
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    if x_management_token and secrets.compare_digest(hashlib.sha256(x_management_token.encode()).hexdigest(), test['creator_management_token_hash']): raise AppError(403,'creator_preview','Creator previews cannot submit listener votes.')
    participant_hash = hashlib.sha256(body.participant_id.encode()).hexdigest()
    assignment = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':participant_hash})
    options = test.get('options') or [{'id':hashlib.sha256(f"{test_id}:{label}".encode()).hexdigest()[:24], 'label':label} for label in [test['intended_label'],*test['distractors']]]
    selected = next((item for item in options if (body.selected_option_id and item['id'] == body.selected_option_id) or (body.selected_label and item['label'] == body.selected_label)), None)
    if not assignment or not selected: raise AppError(422,'invalid_vote','Choose one of the four interpretations shown.')
    correct = selected.get('id') == test.get('intended_option_id') if test.get('intended_option_id') else selected['label'].casefold() == test['intended_label'].casefold()
    try: await db.heardit_votes.insert_one({'id':str(uuid.uuid4()),'test_id':test_id,'anonymous_participant_hash':participant_hash,'assigned_condition':assignment['condition'],'selected_option_id':selected['id'],'selected_label':selected['label'],'correct':correct,'created_at':now()})
    except DuplicateKeyError: raise AppError(409,'already_voted','Your response has already been recorded.')
    return {'submitted':True,'intended_label':test['intended_label'],'correct':correct}

@router.get('/api/v1/tests/{test_id}/results')
async def results(test_id: str, x_management_token: str | None = Header(default=None), db=Depends(require_database)):
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    _require_management_token(test, x_management_token)
    votes = [v async for v in db.heardit_votes.find({'test_id':test_id})]
    def group(condition):
        rows=[v for v in votes if v['assigned_condition']==condition]; n=len(rows); k=sum(v['correct'] for v in rows)
        return {'n':n,'correct':k,'rate':k/n if n else None,'interval':wilson(k,n),'distribution':{label:sum(v['selected_label'].casefold()==label.casefold() for v in rows) for label in [test['intended_label'],*test['distractors']]}}
    audio,text=group('audio'),group('text')
    return {'id':test_id,'intended_label':test['intended_label'],'labels':[test['intended_label'],*test['distractors']],'total':len(votes),'audio':audio,'text':text,'voice_lift':audio['rate']-text['rate'] if audio['rate'] is not None and text['rate'] is not None else None,'preliminary':len(votes)<20,'interpretation':'Exploratory randomized sample; this difference is not proof of a universal voice effect.'}

def wilson(k,n,z=1.959963984540054):
    if not n:return None
    p=k/n; den=1+z*z/n; center=(p+z*z/(2*n))/den; margin=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/den
    return [max(0,center-margin),min(1,center+margin)]

@router.get('/api/v1/audio/{audio_id}')
async def get_audio(audio_id: str, db=Depends(require_database)):
    if not await db.audio_assets.find_one({'id':audio_id}): raise AppError(404,'audio_not_found','Audio not found.')
    asset=await db.audio_assets.find_one({'id':audio_id})
    try: content=await _gridfs(db).open_download_stream(asset['gridfs_id'])
    except Exception as exc: raise AppError(404,'audio_not_found','Audio not found.') from exc
    data=await content.read()
    return Response(data,media_type='audio/mpeg',headers={'Cache-Control':'public,max-age=31536000,immutable','X-Content-Type-Options':'nosniff'})

async def initialize_heardit(db):
    await db.heardit_tests.create_index('id',unique=True)
    await db.audio_assets.create_index('cache_key',unique=True,sparse=True)
    await db.heardit_assignments.create_index([('test_id',ASCENDING),('participant_hash',ASCENDING)],unique=True)
    await db.heardit_votes.create_index([('test_id',ASCENDING),('anonymous_participant_hash',ASCENDING)],unique=True)
    await db.heardit_rate_limits.create_index('expires_at',expireAfterSeconds=0)
