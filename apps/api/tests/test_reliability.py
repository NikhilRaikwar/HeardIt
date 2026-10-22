"""Route-level reliability checks; provider requests are explicitly mocked."""

import asyncio
import copy
import hashlib
import io
import json
import os
import uuid
from types import SimpleNamespace

import httpx
import pytest
from pymongo import AsyncMongoClient
from pydantic import SecretStr
from pymongo.errors import DuplicateKeyError

import app.heardit as heardit
import app.main as main
from app.core.errors import AppError
from app.db import require_database
from app.services.fish_tts import FishTTSService, canonical_speech_text, get_fish_service

MP3 = b'ID3' + bytes(range(128))
CREATOR_TOKEN = 'creator-token-only-for-unit-tests'
SPEECH = {'sentence': 'I thought you would be here.', 'direction': '[curious]'}


def matches(row, query):
    for key, value in query.items():
        if isinstance(value, dict):
            for operator, expected in value.items():
                if operator == '$exists' and (key in row) != expected:
                    return False
                if operator == '$lt' and not row.get(key, 0) < expected:
                    return False
                if operator == '$lte' and not row.get(key, 0) <= expected:
                    return False
                if operator == '$ne' and row.get(key) == expected:
                    return False
        elif row.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self.iterator))
        except StopIteration:
            raise StopAsyncIteration


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.indexes = []
        self.find_one_calls = 0

    async def create_index(self, keys, **options):
        self.indexes.append((keys, options))
        return str(keys)

    async def find_one(self, query, *args, **kwargs):
        self.find_one_calls += 1
        row = next((row for row in self.rows if matches(row, query)), None)
        return copy.deepcopy(row)

    def find(self, query):
        return Cursor([row for row in self.rows if matches(row, query)])

    async def insert_one(self, row):
        await asyncio.sleep(0)
        constraints = [(['_id'], False)]
        for keys, options in self.indexes:
            if options.get('unique'):
                constraints.append(([keys] if isinstance(keys, str) else [key for key, _ in keys], options.get('sparse', False)))
        for keys, sparse in constraints:
            if sparse and any(key not in row for key in keys):
                continue
            if all(key in row for key in keys) and any(all(old.get(key) == row.get(key) for key in keys) for old in self.rows):
                raise DuplicateKeyError('test unique index')
        self.rows.append(copy.deepcopy(row))
        return SimpleNamespace(inserted_id=row.get('_id', row.get('id')))

    async def delete_one(self, query):
        self.rows = [row for row in self.rows if not matches(row, query)]

    async def find_one_and_update(self, query, update, **kwargs):
        row = next((row for row in self.rows if matches(row, query)), None)
        if row is None:
            if not kwargs.get('upsert'):
                return None
            row = {key: value for key, value in query.items() if not isinstance(value, dict)}
            row.update(update.get('$setOnInsert', {}))
            self.rows.append(row)
        row.update(update.get('$set', {}))
        for key, value in update.get('$inc', {}).items():
            row[key] = row.get(key, 0) + value
        return copy.deepcopy(row)


class Database:
    def __init__(self):
        self.heardit_tests = Collection()
        self.heardit_assignments = Collection()
        self.heardit_votes = Collection()
        self.heardit_rate_limits = Collection()
        self.audio_assets = Collection()
        self.events = Collection()

    async def command(self, _command):
        return {'ok': 1}


class Download:
    def __init__(self, data):
        self.source = io.BytesIO(data)
        self.length = len(data)

    async def read(self, size=-1):
        return self.source.read(size)

    async def readchunk(self):
        return self.source.read(64 * 1024)

    async def seek(self, offset, whence=0):
        return self.source.seek(offset, whence)

    async def close(self):
        self.source.close()


class Bucket:
    def __init__(self):
        self.files = {}
        self.deleted = []

    async def upload_from_stream(self, name, data, **kwargs):
        identifier = f'grid-{name}'
        self.files[identifier] = bytes(data)
        return identifier

    async def open_download_stream(self, identifier):
        return Download(self.files[identifier])

    async def delete(self, identifier):
        self.deleted.append(identifier)
        del self.files[identifier]


@pytest.fixture
async def api(monkeypatch):
    db, bucket = Database(), Bucket()
    monkeypatch.setattr(heardit, '_indexes_ready', False)
    settings = heardit.settings.model_copy(update={'fish_api_key': SecretStr('test-only-key'), 'fish_default_voice_id': None})
    monkeypatch.setattr(heardit, 'settings', settings)
    monkeypatch.setattr(heardit, '_gridfs', lambda _db: bucket)

    async def database():
        return db

    main.app.dependency_overrides[require_database] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        yield client, db, bucket, settings
    main.app.dependency_overrides.clear()


def provider_override(client, settings):
    async def no_wait(_seconds):
        pass

    service = FishTTSService(settings, client=client, sleep=no_wait)
    main.app.dependency_overrides[get_fish_service] = lambda: service


def publish_body(audio_id, **overrides):
    return {**SPEECH, 'audio_id': audio_id, 'intended_label': 'Curious', 'distractors': ['Annoyed', 'Hurt', 'Playful'], **overrides}


@pytest.mark.asyncio
@pytest.mark.parametrize(('provider_status', 'code', 'expected_status', 'attempts'), [
    (401, 'fish_authentication_failed', 502, 1),
    (402, 'fish_quota_unavailable', 503, 1),
    (429, 'fish_rate_limited', 429, 3),
    (500, 'fish_unavailable', 503, 3),
    (200, 'fish_invalid_audio', 502, 1),
])
async def test_generate_route_provider_failures_never_save_an_asset(api, provider_status, code, expected_status, attempts):
    client, db, bucket, settings = api
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(provider_status, headers={'content-type': 'application/json'}, json={'error': 'mocked failure'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider:
        provider_override(provider, settings)
        response = await client.post('/api/v1/audio/generate', json=SPEECH)
    assert response.status_code == expected_status, response.text
    assert response.json()['error']['code'] == code
    assert calls == attempts
    assert db.audio_assets.rows == []
    assert bucket.files == {}


@pytest.mark.asyncio
async def test_generate_route_timeout_never_saves_an_asset(api):
    client, db, bucket, settings = api
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout('mocked provider timeout', request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider:
        provider_override(provider, settings)
        response = await client.post('/api/v1/audio/generate', json=SPEECH)
    assert response.status_code == 503, response.text
    assert response.json()['error']['code'] == 'fish_timeout'
    assert calls == 3
    assert db.audio_assets.rows == [] and bucket.files == {}


@pytest.mark.asyncio
async def test_generate_cache_and_publish_share_canonical_whitespace(api):
    client, db, _bucket, settings = api
    requests = []

    async def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': 'audio/mpeg'}, content=MP3)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider:
        provider_override(provider, settings)
        first = await client.post('/api/v1/audio/generate', json={
            'sentence': ' I thought\n you  would be here. ', 'direction': ' [curious] ',
        })
        assert first.status_code == 200, first.text
        second = await client.post('/api/v1/audio/generate', json=SPEECH)
    assert first.json()['audio_id'] == second.json()['audio_id']
    assert second.json()['cached'] is True
    assert requests == [{'text': canonical_speech_text(**{'direction': SPEECH['direction'], 'sentence': SPEECH['sentence']}), 'format': 'mp3'}]
    assert db.audio_assets.rows[0]['input_text'] == '[curious] I thought you would be here.'
    published = await client.post('/api/v1/tests', json=publish_body(first.json()['audio_id']), headers={'Idempotency-Key': 'canonical-publish-key-123456'})
    assert published.status_code == 201, published.text
    assert len(db.heardit_tests.rows) == 1


@pytest.mark.asyncio
async def test_concurrent_identical_generation_keeps_one_asset_and_no_orphans(api):
    client, db, bucket, settings = api

    async def handler(_request):
        await asyncio.sleep(.01)
        return httpx.Response(200, headers={'content-type': 'audio/mpeg'}, content=MP3)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider:
        provider_override(provider, settings)
        responses = await asyncio.gather(*(client.post('/api/v1/audio/generate', json=SPEECH) for _ in range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()['audio_id'] == responses[1].json()['audio_id']
    assert len(db.audio_assets.rows) == len(bucket.files) == 1
    assert set(bucket.files) == {db.audio_assets.rows[0]['gridfs_id']}


@pytest.mark.asyncio
async def test_publish_retry_returns_same_test_and_private_token(api):
    client, db, _bucket, _settings = api
    db.audio_assets.rows.append({'id': 'saved-clip', 'model': 's2.1-pro-free', 'input_text': canonical_speech_text(SPEECH['direction'], SPEECH['sentence'])})
    headers = {'Idempotency-Key': 'publish-retry-key-123456789'}
    first = await client.post('/api/v1/tests', json=publish_body('saved-clip'), headers=headers)
    second = await client.post('/api/v1/tests', json=publish_body('saved-clip'), headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(db.heardit_tests.rows) == 1
    changed = await client.post('/api/v1/tests', json=publish_body('saved-clip', intended_label='Wondering'), headers=headers)
    assert changed.status_code == 409, changed.text


@pytest.mark.asyncio
async def test_audio_is_immutable_and_supports_bounded_ranges(api):
    client, db, bucket, _settings = api
    db.audio_assets.rows.append({'id': 'saved-clip', 'gridfs_id': 'grid-clip', 'file_size': len(MP3)})
    bucket.files['grid-clip'] = MP3
    for requested, expected in [('bytes=0-9', MP3[:10]), ('bytes=10-', MP3[10:]), ('bytes=-8', MP3[-8:])]:
        response = await client.get('/api/v1/audio/saved-clip', headers={'Range': requested})
        assert response.status_code == 206, response.text
        assert response.content == expected
        assert response.headers['accept-ranges'] == 'bytes'
        assert response.headers['content-type'].startswith('audio/mpeg')
        assert 'immutable' in response.headers['cache-control']
        assert int(response.headers['content-length']) == len(expected)
        assert response.headers['content-range'].endswith(f'/{len(MP3)}')
    assert db.audio_assets.find_one_calls == 3
    full = await client.get('/api/v1/audio/saved-clip')
    assert full.status_code == 200 and full.content == MP3
    invalid = await client.get('/api/v1/audio/saved-clip', headers={'Range': f'bytes={len(MP3)}-'})
    assert invalid.status_code == 416
    assert invalid.headers['content-range'] == f'bytes */{len(MP3)}'


@pytest.mark.asyncio
async def test_lazy_index_gate_recovers_after_startup_database_outage(api, monkeypatch):
    client, db, _bucket, _settings = api

    async def unavailable():
        raise AppError(503, 'database_unavailable', 'Mock MongoDB unavailable at startup')

    monkeypatch.setattr(main, 'require_database', unavailable)
    async with main.lifespan(main.app):
        assert db.heardit_votes.indexes == []
        db.heardit_tests.rows.append({'id': 'recovered-test', 'status': 'published', 'creator_management_token_hash': hashlib.sha256(CREATOR_TOKEN.encode()).hexdigest()})
        response = await client.post('/api/v1/tests/recovered-test/assignment', json={'participant_id': 'x' * 48})
        assert response.status_code == 200, response.text
        assert any(options.get('unique') for _, options in db.heardit_votes.indexes)
        assert any(options.get('expireAfterSeconds') == 0 for _, options in db.heardit_rate_limits.indexes)
        health = await client.get('/health')
        assert health.status_code == 200 and health.json()['indexes_ready'] is True


@pytest.mark.asyncio
async def test_real_mongo_recovers_after_startup_outage_and_indexes_before_vote(monkeypatch):
    uri = os.environ.get('HEARDIT_MONGO_TEST_URI')
    if not uri:
        pytest.skip('Set HEARDIT_MONGO_TEST_URI to run the isolated real-Mongo integration check.')
    mongo = AsyncMongoClient(uri, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
    database_name = f'heardit_phase2_{uuid.uuid4().hex}'
    db = mongo[database_name]
    monkeypatch.setattr(heardit, '_indexes_ready', False)

    async def unavailable():
        raise AppError(503, 'database_unavailable', 'Simulated MongoDB startup outage')

    async def available():
        await db.command('ping')
        return db

    monkeypatch.setattr(main, 'require_database', unavailable)
    try:
        async with main.lifespan(main.app):
            main.app.dependency_overrides[require_database] = available
            test_id = 'real-mongo-index-test'
            await db.heardit_tests.insert_one({
                'id':test_id,
                'status':'published',
                'sentence':'A real Mongo-backed assignment.',
                'intended_label':'Curious',
                'distractors':['Annoyed','Hurt','Playful'],
            })
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
                before = await client.get('/health')
                assert before.status_code == 200 and before.json()['indexes_ready'] is False
                participant = 'real-mongo-participant-1234567890'
                assignment = await client.post(f'/api/v1/tests/{test_id}/assignment', json={'participant_id':participant})
                assert assignment.status_code == 200, assignment.text

                vote_cursor = await db.heardit_votes.list_indexes()
                vote_indexes = await vote_cursor.to_list(length=None)
                assert any(index.get('unique') and index['key'].get('test_id') == 1 and index['key'].get('anonymous_participant_hash') == 1 for index in vote_indexes)
                rate_cursor = await db.heardit_rate_limits.list_indexes()
                rate_indexes = await rate_cursor.to_list(length=None)
                assert any(index.get('expireAfterSeconds') == 0 for index in rate_indexes)

                vote = await client.post(f'/api/v1/tests/{test_id}/votes', json={
                    'participant_id':participant,
                    'assignment_token':assignment.json()['assignment_token'],
                    'selected_label':'Curious',
                })
                assert vote.status_code == 201, vote.text
                health = await client.get('/health')
                assert health.json()['indexes_ready'] is True
    finally:
        main.app.dependency_overrides.clear()
        await mongo.drop_database(database_name)
        await mongo.close()
