"""Boundary tests use real ASGI routing, validation and signed assignment tokens."""
import base64
import hashlib
import json
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

import app.routers.heardit as experiments
from app.core.config import Settings
from app.db import require_database
from app.main import app
from test_heardit import FakeDB, MANAGEMENT_TOKEN, assigned_session, request


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
async def client(db, monkeypatch):
    monkeypatch.setattr(experiments, '_indexes_ready', False)
    app.dependency_overrides[require_database] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as value:
        yield value
    app.dependency_overrides.clear()


async def start(client, participant='p' * 48):
    response = await client.post('/api/v1/tests/test-1/assignment', json={'participant_id':participant})
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_legitimate_flow_and_replayed_token_cannot_insert_second_vote(client, db):
    session = await start(client)
    public = await client.get('/api/v1/tests/test-1/public', params={'participant_id':'p'*48}, headers={'X-Assignment-Token':session['assignment_token']})
    assert public.status_code == 200
    assert 'intended_label' not in public.json() and 'direction' not in public.json()
    body = {'participant_id':'p'*48, 'assignment_token':session['assignment_token'], 'selected_option_id':public.json()['options'][0]['id']}
    first = await client.post('/api/v1/tests/test-1/votes', json=body)
    second = await client.post('/api/v1/tests/test-1/votes', json=body)
    assert first.status_code == 201 and second.status_code == 409
    assert len(db.heardit_votes.rows) == 1


@pytest.mark.asyncio
async def test_forged_missing_and_mismatched_tokens_rejected_before_vote(client, db):
    session = await start(client)
    encoded, signature = session['assignment_token'].split('.')
    payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    payload['condition'] = 'text' if payload['condition'] == 'audio' else 'audio'
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=') + '.' + signature
    for participant, token in [('p'*48, forged), ('z'*48, session['assignment_token']), ('p'*48, '')]:
        public = await client.get('/api/v1/tests/test-1/public', params={'participant_id':participant}, headers={'X-Assignment-Token':token})
        assert public.status_code == 401
    vote = await client.post('/api/v1/tests/test-1/votes', json={'participant_id':'p'*48,'assignment_token':forged,'selected_label':'Sarcastic'})
    assert vote.status_code == 401 and db.heardit_votes.rows == []


@pytest.mark.asyncio
async def test_valid_signature_cannot_override_saved_condition(client, db):
    session = await start(client)
    condition = 'text' if session['condition'] == 'audio' else 'audio'
    token = experiments._assignment_token('test-1', hashlib.sha256(('p'*48).encode()).hexdigest(), condition, int(datetime.now(timezone.utc).timestamp()))
    response = await client.get('/api/v1/tests/test-1/public', params={'participant_id':'p'*48}, headers={'X-Assignment-Token':token})
    assert response.status_code == 401
    response = await client.post('/api/v1/tests/test-1/assignment', json={'participant_id':'p'*48,'condition':condition})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tokens_are_bound_to_test_and_expire(client, db):
    await start(client)
    hashed = hashlib.sha256(('p'*48).encode()).hexdigest()
    for test_id, issued in [('other-test', int(datetime.now(timezone.utc).timestamp())), ('test-1', 1)]:
        token = experiments._assignment_token(test_id, hashed, db.heardit_assignments.rows[0]['condition'], issued)
        response = await client.get('/api/v1/tests/test-1/public', params={'participant_id':'p'*48}, headers={'X-Assignment-Token':token})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_write_routes_enforce_burst_limits(client, db, monkeypatch):
    monkeypatch.setattr(experiments.settings, 'publish_ip_hourly', 1)
    monkeypatch.setattr(experiments.settings, 'assignment_ip_minute', 1)
    monkeypatch.setattr(experiments.settings, 'vote_ip_minute', 1)
    payload = {'sentence':'I thought you would be here.','intended_label':'Sarcastic','distractors':['Pleased','Sad','Angry'],'direction':'[dry]','audio_id':'audio-1'}
    assert (await client.post('/api/v1/tests', json=payload)).status_code == 201
    assert (await client.post('/api/v1/tests', json=payload)).status_code == 429
    session = await start(client)
    assert (await client.post('/api/v1/tests/test-1/assignment', json={'participant_id':'q'*48})).status_code == 429
    vote = {'participant_id':'p'*48, 'assignment_token':session['assignment_token'], 'selected_label':'Sarcastic'}
    assert (await client.post('/api/v1/tests/test-1/votes', json=vote)).status_code == 201
    assert (await client.post('/api/v1/tests/test-1/votes', json=vote)).status_code == 429


@pytest.mark.asyncio
async def test_test_caps_apply_across_ip_buckets(db, monkeypatch):
    monkeypatch.setattr(experiments.settings, 'assignment_test_minute', 1)
    await assigned_session(db, 'p'*48)
    with pytest.raises(experiments.AppError) as caught:
        await experiments.assignment('test-1', experiments.AssignmentRequest(participant_id='q'*48), request(ip='192.0.2.2'), x_management_token=None, db=db)
    assert caught.value.status == 429


@pytest.mark.asyncio
async def test_daily_publish_and_per_test_vote_caps(client, db, monkeypatch):
    monkeypatch.setattr(experiments.settings, 'tests_daily_cap', 1)
    monkeypatch.setattr(experiments.settings, 'votes_per_test_daily_cap', 1)
    payload = {'sentence':'I thought you would be here.','intended_label':'Sarcastic','distractors':['Pleased','Sad','Angry'],'direction':'[dry]','audio_id':'audio-1'}
    assert (await client.post('/api/v1/tests', json=payload)).status_code == 201
    assert (await client.post('/api/v1/tests', json=payload)).status_code == 429
    for index, participant in enumerate(['p'*48, 'q'*48]):
        session = await start(client, participant)
        response = await client.post('/api/v1/tests/test-1/votes', json={'participant_id':participant,'assignment_token':session['assignment_token'],'selected_label':'Sarcastic'})
        assert response.status_code == (201 if index == 0 else 429)


def test_untrusted_forwarded_headers_cannot_rotate_ip(monkeypatch):
    monkeypatch.setattr(experiments.settings, 'trust_proxy', False)
    assert experiments.client_ip(request([('X-Forwarded-For','203.0.113.5')])) == '192.0.2.1'
    assert experiments.client_ip(request([('X-Forwarded-For','forged')])) == '192.0.2.1'


def test_trusted_proxy_uses_validated_forwarded_address(monkeypatch):
    monkeypatch.setattr(experiments.settings, 'trust_proxy', True)
    assert experiments.client_ip(request([('X-Forwarded-For','203.0.113.5, 192.0.2.8')])) == '203.0.113.5'
    with pytest.raises(experiments.AppError):
        experiments.client_ip(request([('X-Forwarded-For','forged')]))


@pytest.mark.asyncio
async def test_creator_preview_never_assigns_or_votes(client, db):
    response = await client.post('/api/v1/tests/test-1/assignment', json={'participant_id':'p'*48}, headers={'X-Management-Token':MANAGEMENT_TOKEN})
    assert response.status_code == 200
    assert response.json() == {'creator_preview':True,'condition':'audio','assignment_token':None}
    assert db.heardit_assignments.rows == [] and db.heardit_votes.rows == []
    session = await start(client)
    response = await client.post('/api/v1/tests/test-1/votes', json={'participant_id':'p'*48,'assignment_token':session['assignment_token'],'selected_label':'Sarcastic'}, headers={'X-Management-Token':MANAGEMENT_TOKEN})
    assert response.status_code == 403 and db.heardit_votes.rows == []


@pytest.mark.asyncio
async def test_optional_captcha_is_off_by_default_and_enforced_only_when_enabled(client, monkeypatch):
    monkeypatch.setattr(experiments.settings, 'captcha_enabled', False)
    assert (await start(client))['assignment_token']
    monkeypatch.setattr(experiments.settings, 'captcha_enabled', True)
    from pydantic import SecretStr
    monkeypatch.setattr(experiments.settings, 'turnstile_secret', SecretStr('test-only-secret'))
    response = await client.post('/api/v1/tests/test-1/assignment', json={'participant_id':'q'*48})
    assert response.status_code == 422 and response.json()['error']['code'] == 'captcha_required'


def test_production_requires_explicit_strong_signing_secret():
    with pytest.raises(ValidationError, match='HEARDIT_SIGNING_SECRET'):
        Settings(_env_file=None, HEARDIT_ENV='production', HEARDIT_SIGNING_SECRET='')
    assert Settings(_env_file=None, HEARDIT_ENV='production', HEARDIT_SIGNING_SECRET='s'*48).environment == 'production'
