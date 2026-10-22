"""HeardIt's public, privacy-preserving listening experiment API."""
import asyncio
import base64, binascii, hashlib, hmac, ipaddress, json, re, secrets, uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument
from gridfs import AsyncGridFSBucket

from app.core.config import get_settings
from app.core.errors import AppError
from app.db import require_database
from app.services.fish_tts import (
    FishTTSService,
    canonical_speech_text,
    get_fish_service,
    synthesis_cache_key,
)

router = APIRouter()
settings = get_settings()
now = lambda: datetime.now(timezone.utc).isoformat()
_indexes_ready = False
_indexes_lock = asyncio.Lock()


def indexes_ready() -> bool:
    return _indexes_ready


async def ensure_indexes(db):
    """Create the uniqueness/TTL guarantees before accepting the first write."""
    global _indexes_ready
    if _indexes_ready:
        return
    async with _indexes_lock:
        if _indexes_ready:
            return
        await initialize_heardit(db)
        _indexes_ready = True


async def require_indexed_database(db=Depends(require_database)):
    await ensure_indexes(db)
    return db

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
    assignment_token: str = Field(min_length=1, max_length=2048)
    selected_option_id: str | None = Field(default=None, min_length=1, max_length=64)
    selected_label: str | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode='after')
    def one_selection(self):
        if bool(self.selected_option_id) == bool(self.selected_label):
            raise ValueError('Choose exactly one answer option.')
        return self

class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participant_id: str = Field(min_length=24, max_length=128)
    captcha_token: str | None = Field(default=None, max_length=4096)

def client_ip(request: Request) -> str:
    """Forwarded addresses are trustworthy only behind a sanitizing trusted proxy."""
    peer = request.client.host if request.client else 'unknown'
    forwarded = request.headers.get('x-forwarded-for') if settings.trust_proxy else None
    if not forwarded:
        return peer
    addresses = [value.strip() for value in forwarded.split(',')]
    try:
        if len(addresses) > 10:
            raise ValueError('Too many proxy hops')
        parsed = [str(ipaddress.ip_address(value)) for value in addresses]
    except ValueError as exc:
        raise AppError(400, 'invalid_forwarded_ip', 'The proxy supplied an invalid client address.') from exc
    return parsed[0]

def _ip_hash(request: Request) -> str:
    return hashlib.sha256(client_ip(request).encode()).hexdigest()

def _assignment_token(test_id: str, participant_hash: str, condition: str, issued_at: int) -> str:
    payload = {'test_id':test_id, 'participant_hash':participant_hash, 'condition':condition, 'issued_at':issued_at}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).decode().rstrip('=')
    signature = hmac.new(settings.signing_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f'{encoded}.{signature}'

def _verify_assignment_token(token: str | None, test_id: str, participant_hash: str) -> dict:
    try:
        if not token or len(token) > 2048:
            raise ValueError('Missing token')
        encoded, signature = token.split('.')
        expected = hmac.new(settings.signing_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid signature')
        payload = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
        timestamp = int(datetime.now(timezone.utc).timestamp())
        if (set(payload) != {'test_id','participant_hash','condition','issued_at'}
                or payload['test_id'] != test_id or payload['participant_hash'] != participant_hash
                or payload['condition'] not in ('audio','text') or type(payload['issued_at']) is not int
                or not 0 <= timestamp - payload['issued_at'] <= settings.assignment_token_max_age):
            raise ValueError('Token does not match this assignment')
        return payload
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error) as exc:
        raise AppError(401, 'invalid_assignment_token', 'Your listening session is invalid or expired. Reopen the test.') from exc

async def _verified_assignment(db, test_id: str, participant: str, token: str | None):
    participant_hash = hashlib.sha256(participant.encode()).hexdigest()
    payload = _verify_assignment_token(token, test_id, participant_hash)
    row = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':participant_hash})
    if not row or row['condition'] != payload['condition']:
        raise AppError(401, 'invalid_assignment_token', 'Your listening session no longer matches its saved assignment.')
    return participant_hash, row

async def _verify_captcha(token: str | None, request: Request):
    if not settings.captcha_enabled:
        return
    key = settings.turnstile_secret.get_secret_value()
    if not key:
        raise AppError(503, 'captcha_unavailable', 'Listener verification is temporarily unavailable.')
    if not token:
        raise AppError(422, 'captcha_required', 'Complete listener verification before continuing.')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data={'secret':key,'response':token,'remoteip':client_ip(request)})
            valid = response.is_success and response.json().get('success') is True
    except (httpx.HTTPError, ValueError):
        raise AppError(503, 'captcha_unavailable', 'Listener verification could not connect. Try again.')
    if not valid:
        raise AppError(422, 'captcha_rejected', 'Listener verification failed. Try again.')

def _db(db):
    return db

def _gridfs(db):
    return AsyncGridFSBucket(db, bucket_name='heardit_audio')

def _cache_key(sentence, direction):
    return synthesis_cache_key(direction, sentence, settings.fish_tts_model, settings.fish_default_voice_id)

@router.get('/health')
async def health(db=Depends(require_database)):
    return {'status': 'ok', 'database': 'mongodb', 'fish_configured': bool(settings.fish_api_key.get_secret_value()), 'indexes_ready': indexes_ready()}

@router.post('/api/v1/suggestions')
async def suggestions(body: SuggestRequest, request: Request, db=Depends(require_indexed_database)):
    if not settings.aiml_api_key.get_secret_value():
        raise AppError(503, 'aiml_not_configured', 'AI suggestions are unavailable right now. Add interpretations manually and continue.')
    await _rate_limit(db, 'suggest:' + _ip_hash(request), 30)
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
async def generate(body: GenerateRequest, request: Request, db=Depends(require_indexed_database), fish: FishTTSService=Depends(get_fish_service)):
    await _rate_limit(db, 'generate:' + _ip_hash(request), 10)
    cache = _cache_key(body.sentence, body.direction)
    cached = await db.audio_assets.find_one({'cache_key': cache})
    if cached:
        return _audio_payload(cached, cached=True)
    full_text = canonical_speech_text(body.direction, body.sentence)
    audio = await fish.generate(full_text, language='en', voice_id=settings.fish_default_voice_id)
    audio_id = str(uuid.uuid4())
    created_at = now()
    bucket = _gridfs(db)
    grid_id = None
    try:
        grid_id = await bucket.upload_from_stream(audio_id, audio, metadata={'contentType':'audio/mpeg','cache_key':cache})
        asset = {
            'id':audio_id,
            'gridfs_id':grid_id,
            'cache_key':cache,
            'content_type':'audio/mpeg',
            'storage_reference':str(grid_id),
            'file_size':len(audio),
            'model':settings.fish_tts_model,
            'direction':' '.join(body.direction.split()),
            'voice':settings.fish_default_voice_id or 'fish-account-default-v1',
            'input_text':full_text,
            'created_at':created_at,
        }
        await db.audio_assets.insert_one(asset)
    except DuplicateKeyError:
        # Another request won the cache-key race after this request uploaded.
        if grid_id is not None:
            await bucket.delete(grid_id)
        winner = await db.audio_assets.find_one({'cache_key':cache})
        if winner:
            return _audio_payload(winner, cached=True)
        raise AppError(503, 'audio_storage_failed', 'The generated clip could not be saved. It is not ready to publish.')
    except Exception as exc:
        if grid_id is not None:
            try:
                await bucket.delete(grid_id)
            except Exception:
                pass
        raise AppError(503, 'audio_storage_failed', 'The generated clip could not be saved. It is not ready to publish.') from exc
    return _audio_payload(asset, cached=False)


def _audio_payload(asset, cached: bool):
    return {
        'audio_id':asset['id'],
        'url':f"/api/v1/audio/{asset['id']}",
        'cached':cached,
        'model':asset['model'],
        'direction':asset['direction'],
        'voice':asset['voice'],
        'created_at':asset['created_at'],
    }

async def _rate_limit(db, key, max_count, seconds=3600):
    from datetime import timedelta
    window = int(datetime.now(timezone.utc).timestamp()) // seconds
    result = await db.heardit_rate_limits.find_one_and_update({'_id':f'{key}:{window}'},{'$inc':{'count':1},'$setOnInsert':{'expires_at':datetime.now(timezone.utc)+timedelta(seconds=seconds*2)}},upsert=True,return_document=ReturnDocument.AFTER)
    if result['count'] > max_count: raise AppError(429,'rate_limited','Too many requests. Please try again later.')

@router.post('/api/v1/tests', status_code=201)
async def create_test(
    body: CreateTest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    db=Depends(require_indexed_database),
):
    await _rate_limit(db, 'publish:ip:' + _ip_hash(request), settings.publish_ip_hourly)
    key_hash = None
    request_hash = None
    if idempotency_key is not None:
        if not re.fullmatch(r'[A-Za-z0-9._~-]{16,128}', idempotency_key):
            raise AppError(422, 'invalid_idempotency_key', 'Idempotency-Key must be 16 to 128 URL-safe characters.')
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_hash = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        existing = await db.heardit_tests.find_one({'idempotency_key_hash':key_hash})
        if existing:
            if existing.get('publish_request_hash') != request_hash:
                raise AppError(409, 'idempotency_conflict', 'This publish key was already used for different test settings.')
            return _publish_payload(existing, key_hash)
    await _rate_limit(db, 'publish:audio:' + body.audio_id, settings.publish_audio_hourly)
    await _rate_limit(db, 'publish:global', settings.tests_daily_cap, 86400)
    asset = await db.audio_assets.find_one({'id':body.audio_id})
    if not asset: raise AppError(422,'audio_required','Generate and save audio before publishing this test.')
    if asset.get('input_text') != canonical_speech_text(body.direction, body.sentence): raise AppError(422,'audio_mismatch','Generate audio for the current sentence and direction before publishing.')
    test_id = secrets.token_urlsafe(12)
    token = _idempotent_management_token(test_id, key_hash) if key_hash else secrets.token_urlsafe(32)
    labels = [body.intended_label.strip(), *body.distractors]
    descriptions = body.option_descriptions or ['', '', '', '']
    options = [{'id':str(uuid.uuid4()), 'label':label, 'description':description} for label, description in zip(labels, descriptions)]
    doc = {
        'id':test_id,
        'sentence':body.sentence.strip(),
        'intended_label':body.intended_label.strip(),
        'intended_option_id':options[0]['id'],
        'distractors':body.distractors,
        'options':options,
        'direction':' '.join(body.direction.split()),
        'model':asset['model'],
        'audio_id':asset['id'],
        'creator_management_token_hash':hashlib.sha256(token.encode()).hexdigest(),
        'status':'published',
        'created_at':now(),
    }
    if key_hash:
        doc['idempotency_key_hash'] = key_hash
        doc['publish_request_hash'] = request_hash
    try:
        await db.heardit_tests.insert_one(doc)
    except DuplicateKeyError:
        if key_hash:
            winner = await db.heardit_tests.find_one({'idempotency_key_hash':key_hash})
            if winner:
                if winner.get('publish_request_hash') != request_hash:
                    raise AppError(409, 'idempotency_conflict', 'This publish key was already used for different test settings.')
                return _publish_payload(winner, key_hash)
        raise AppError(409, 'publish_conflict', 'This test could not be published because its identifier already exists. Retry with a new key.')
    return _publish_payload(doc, key_hash, token)


def _idempotent_management_token(test_id: str, key_hash: str | None) -> str:
    secret = settings.signing_secret.get_secret_value().encode()
    digest = hmac.new(secret, f'heardit-management-v1:{test_id}:{key_hash}'.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')


def _publish_payload(doc, key_hash: str | None, token: str | None = None):
    if key_hash:
        token = _idempotent_management_token(doc['id'], key_hash)
    return {'id':doc['id'],'management_token':token,'status':doc['status']}

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
async def public_test(test_id: str, participant_id: str, x_assignment_token: str | None = Header(default=None), db=Depends(require_database)):
    doc = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not doc: raise AppError(404,'test_not_found','This listening test could not be found.')
    _, assigned = await _verified_assignment(db, test_id, participant_id, x_assignment_token)
    options = doc.get('options') or [{'id':hashlib.sha256(f"{test_id}:{label}".encode()).hexdigest()[:24], 'label':label, 'description':''} for label in [doc['intended_label'],*doc['distractors']]]
    secrets.SystemRandom().shuffle(options)
    result = {'id':doc['id'],'options':options,'labels':[item['label'] for item in options],'condition':assigned['condition']}
    if assigned['condition'] == 'audio': result['audio_url'] = f"/api/v1/audio/{doc['audio_id']}"
    else: result['sentence'] = doc['sentence']
    return result

@router.post('/api/v1/tests/{test_id}/assignment')
async def assignment(test_id: str, body: AssignmentRequest, request: Request, x_management_token: str | None = Header(default=None), db=Depends(require_indexed_database)):
    participant = body.participant_id
    await _rate_limit(db, 'assignment:ip:' + _ip_hash(request), settings.assignment_ip_minute, 60)
    await _rate_limit(db, 'assignment:test:' + test_id, settings.assignment_test_minute, 60)
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    if x_management_token and secrets.compare_digest(hashlib.sha256(x_management_token.encode()).hexdigest(), test['creator_management_token_hash']):
        return {'creator_preview':True, 'condition':'audio', 'assignment_token':None}
    await _verify_captcha(body.captcha_token, request)
    hashed = hashlib.sha256(participant.encode()).hexdigest()
    row = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':hashed})
    if not row:
        # Insert-once assignment is stable under concurrent refreshes.
        condition = secrets.choice(['audio','text'])
        try: await db.heardit_assignments.insert_one({'test_id':test_id,'participant_hash':hashed,'condition':condition,'issued_at':int(datetime.now(timezone.utc).timestamp()),'created_at':now()})
        except DuplicateKeyError: pass
        row = await db.heardit_assignments.find_one({'test_id':test_id,'participant_hash':hashed})
    # Refreshing an expired token retains the persisted experimental condition.
    issued_at = int(datetime.now(timezone.utc).timestamp())
    return {'condition':row['condition'], 'assignment_token':_assignment_token(test_id, hashed, row['condition'], issued_at), 'creator_preview':False}

@router.post('/api/v1/tests/{test_id}/votes', status_code=201)
async def vote(test_id: str, body: VoteRequest, request: Request, x_management_token: str | None = Header(default=None), db=Depends(require_indexed_database)):
    await _rate_limit(db, 'vote:ip:' + _ip_hash(request), settings.vote_ip_minute, 60)
    await _rate_limit(db, 'vote:test:' + test_id, settings.vote_test_minute, 60)
    await _rate_limit(db, 'vote:test:daily:' + test_id, settings.votes_per_test_daily_cap, 86400)
    test = await db.heardit_tests.find_one({'id':test_id,'status':'published'})
    if not test: raise AppError(404,'test_not_found','This listening test could not be found.')
    if x_management_token and secrets.compare_digest(hashlib.sha256(x_management_token.encode()).hexdigest(), test['creator_management_token_hash']): raise AppError(403,'creator_preview','Creator previews cannot submit listener votes.')
    participant_hash, assignment = await _verified_assignment(db, test_id, body.participant_id, body.assignment_token)
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
async def get_audio(audio_id: str, request: Request, db=Depends(require_database)):
    asset = await db.audio_assets.find_one({'id':audio_id})
    if not asset:
        raise AppError(404, 'audio_not_found', 'Audio not found.')
    try:
        content = await _gridfs(db).open_download_stream(asset['gridfs_id'])
    except Exception as exc:
        raise AppError(404, 'audio_not_found', 'Audio not found.') from exc

    total = int(asset.get('file_size') or content.length)
    if total <= 0:
        await content.close()
        raise AppError(404, 'audio_not_found', 'Audio not found.')
    start, end = 0, total - 1
    status_code = 200
    range_header = request.headers.get('range')
    headers = {
        'Accept-Ranges':'bytes',
        'Cache-Control':'public, max-age=31536000, immutable',
        'X-Content-Type-Options':'nosniff',
        'Content-Length':str(total),
    }
    if range_header:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
        if not match or not any(match.groups()):
            await content.close()
            return Response(status_code=416, headers={**headers, 'Content-Length':'0', 'Content-Range':f'bytes */{total}'})
        first, last = match.groups()
        if not first:
            suffix_length = int(last)
            if suffix_length <= 0:
                await content.close()
                return Response(status_code=416, headers={**headers, 'Content-Length':'0', 'Content-Range':f'bytes */{total}'})
            start = max(0, total - suffix_length)
        else:
            start = int(first)
            end = min(total - 1, int(last)) if last else total - 1
        if start >= total or start > end:
            await content.close()
            return Response(status_code=416, headers={**headers, 'Content-Length':'0', 'Content-Range':f'bytes */{total}'})
        status_code = 206
        headers['Content-Range'] = f'bytes {start}-{end}/{total}'
        headers['Content-Length'] = str(end - start + 1)

    await content.seek(start)

    async def audio_chunks():
        remaining = end - start + 1
        try:
            while remaining:
                chunk = await content.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            await content.close()

    return StreamingResponse(
        audio_chunks(),
        status_code=status_code,
        media_type=asset.get('content_type') or 'audio/mpeg',
        headers=headers,
    )

async def initialize_heardit(db):
    await db.heardit_tests.create_index('id',unique=True)
    await db.heardit_tests.create_index('idempotency_key_hash',unique=True,sparse=True)
    await db.audio_assets.create_index('cache_key',unique=True,sparse=True)
    await db.heardit_assignments.create_index([('test_id',ASCENDING),('participant_hash',ASCENDING)],unique=True)
    await db.heardit_votes.create_index([('test_id',ASCENDING),('anonymous_participant_hash',ASCENDING)],unique=True)
    await db.heardit_rate_limits.create_index('expires_at',expireAfterSeconds=0)
