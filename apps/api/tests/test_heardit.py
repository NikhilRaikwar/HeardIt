import hashlib

import pytest
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request

from app.core.errors import AppError
from app.routers.heardit import _cache_key, assignment, public_product_stats, public_test, results, vote
from app.schemas.heardit import AssignmentRequest, CreateTest, Suggestion, VoteRequest
from app.services.statistics import wilson

MANAGEMENT_TOKEN = 'creator-management-token-for-tests'


class FakeCursor:
    def __init__(self, items): self.items = items
    def __aiter__(self): self.iterator = iter(self.items); return self
    async def __anext__(self):
        try: return next(self.iterator)
        except StopIteration: raise StopAsyncIteration


class FakeCollection:
    def __init__(self, rows=(), unique=()): self.rows = list(rows); self.unique = unique
    async def create_index(self, keys, **options): return str(keys)
    async def find_one(self, query):
        return next((row for row in self.rows if all(row.get(k) == v for k,v in query.items())), None)
    async def insert_one(self, row):
        if self.unique and any(all(old.get(k) == row.get(k) for k in self.unique) for old in self.rows): raise DuplicateKeyError('duplicate')
        self.rows.append(row)
    def find(self, query): return FakeCursor([r for r in self.rows if all(r.get(k) == v for k,v in query.items())])
    async def find_one_and_update(self, query, update, **kwargs):
        row = await self.find_one(query)
        if row is None:
            row = {**query, **update.get('$setOnInsert', {})}
            self.rows.append(row)
        for key, value in update.get('$inc', {}).items(): row[key] = row.get(key, 0) + value
        return row
    async def aggregate(self, pipeline):
        test_id = pipeline[0]['$match']['test_id']
        counts = {}
        for row in self.rows:
            if row.get('test_id') != test_id:
                continue
            key = (row['assigned_condition'], row['selected_label'])
            aggregate = counts.setdefault(key, {'count': 0, 'correct': 0})
            aggregate['count'] += 1
            aggregate['correct'] += int(row['correct'])
        return FakeCursor([
            {'_id': {'condition': condition, 'selected_label': label}, **aggregate}
            for (condition, label), aggregate in sorted(counts.items())
        ])
    async def count_documents(self, query):
        return sum(all(row.get(key) == value for key, value in query.items()) for row in self.rows)
    async def distinct(self, key):
        return list(dict.fromkeys(row[key] for row in self.rows if key in row))


class FakeDB:
    def __init__(self):
        self.heardit_tests = FakeCollection([{'id':'test-1','status':'published','sentence':'I thought you would be here.','intended_label':'Sarcastic','distractors':['Pleased','Sad','Angry'],'audio_id':'audio-1','creator_management_token_hash':hashlib.sha256(MANAGEMENT_TOKEN.encode()).hexdigest()}])
        self.heardit_assignments = FakeCollection(unique=('test_id','participant_hash'))
        self.heardit_votes = FakeCollection(unique=('test_id','anonymous_participant_hash'))
        self.audio_assets = FakeCollection([{'id':'audio-1','model':'s2.1-pro-free','input_text':'[dry] I thought you would be here.'}])
        self.heardit_rate_limits = FakeCollection(unique=('_id',))


def request(headers=(), ip='192.0.2.1'):
    return Request({'type':'http', 'method':'POST', 'path':'/', 'headers':[(key.lower().encode(), value.encode()) for key, value in headers], 'client':(ip, 1234)})


async def assigned_session(db, participant):
    return await assignment('test-1', AssignmentRequest(participant_id=participant), request(), x_management_token=None, db=db)


def test_suggestion_requires_four_distinct_interpretations():
    suggestion = Suggestion.model_validate({
        'intended_label': 'Sarcastic',
        'alternative_labels': ['Genuinely pleased', 'Disappointed', 'Annoyed'],
        'fish_direction': '[dry, sarcastic]',
        'explanation': 'A restrained sarcastic direction.',
    })
    assert len({suggestion.intended_label.casefold(), *(x.casefold() for x in suggestion.alternative_labels)}) == 4
    with pytest.raises(ValidationError):
        Suggestion.model_validate({
            'intended_label': 'Sarcastic',
            'alternative_labels': ['sarcastic', 'Disappointed', 'Annoyed'],
            'fish_direction': '[dry]',
            'explanation': 'Distinct choices are required.',
        })


def test_create_requires_exactly_three_distinct_alternatives():
    payload = {'sentence':'I thought you said you would be here.','intended_label':'Sarcastic','distractors':['Pleased','Sad','Angry'],'direction':'[dry]','audio_id':'asset-1'}
    assert len(CreateTest.model_validate(payload).distractors) == 3
    with pytest.raises(ValidationError):
        CreateTest.model_validate({**payload, 'distractors':['Pleased','pleased','Angry']})


def test_audio_cache_key_includes_synthesis_inputs_and_normalizes_whitespace():
    assert _cache_key('Hello   there.', '[warm]') == _cache_key('Hello there.', '[warm]')
    assert _cache_key('Hello there.', '[warm]') != _cache_key('Hello there.', '[angry]')


def test_wilson_interval_and_zero_response_behavior():
    assert wilson(0, 0) is None
    interval = wilson(5, 10)
    assert interval is not None
    assert 0 < interval[0] < 0.5 < interval[1] < 1
    assert wilson(10, 10)[0] < 1


@pytest.mark.asyncio
async def test_assignment_is_stable_and_public_payload_hides_other_condition():
    db = FakeDB(); participant = 'p' * 48
    first = await assigned_session(db, participant)
    second = await assigned_session(db, participant)
    assert first['condition'] == second['condition']
    public = await public_test('test-1', participant_id=participant, x_assignment_token=first['assignment_token'], db=db)
    assert public['condition'] == first['condition']
    if first['condition'] == 'audio':
        assert 'sentence' not in public and 'audio_url' in public
    else:
        assert 'audio_url' not in public and 'sentence' in public
    assert 'intended_label' not in public and 'direction' not in public


@pytest.mark.asyncio
async def test_vote_is_deduplicated_and_results_aggregate_saved_votes():
    db = FakeDB(); participant = 'v' * 48
    session = await assigned_session(db, participant)
    assigned = db.heardit_assignments.rows[0]['condition']
    options = await public_test('test-1', participant_id=participant, x_assignment_token=session['assignment_token'], db=db)
    selected = next(option for option in options['options'] if option['label'] == 'Sarcastic')
    body = VoteRequest(participant_id=participant, assignment_token=session['assignment_token'], selected_option_id=selected['id'])
    await vote('test-1', body, request(), x_management_token=None, db=db)
    with pytest.raises(AppError) as error:
        await vote('test-1', body, request(), x_management_token=None, db=db)
    assert error.value.code == 'already_voted'
    with pytest.raises(AppError) as unauthorized:
        await results('test-1', x_management_token=None, db=db)
    assert unauthorized.value.code == 'creator_access_required'
    summary = await results('test-1', x_management_token=MANAGEMENT_TOKEN, db=db)
    assert summary['total'] == 1 and summary['preliminary']
    assert summary[assigned]['n'] == 1 and summary[assigned]['correct'] == 1
    assert summary['voice_lift'] is None


@pytest.mark.asyncio
async def test_zero_response_results_return_insufficient_group_data():
    summary = await results('test-1', x_management_token=MANAGEMENT_TOKEN, db=FakeDB())
    assert summary['total'] == 0
    assert summary['audio']['rate'] is None and summary['text']['rate'] is None
    assert summary['voice_lift'] is None and summary['preliminary']


@pytest.mark.asyncio
async def test_mongodb_result_aggregation_matches_previous_python_output():
    db = FakeDB()
    db.heardit_votes.rows = [
        {'test_id':'test-1','assigned_condition':'audio','selected_label':'Sarcastic','correct':True},
        {'test_id':'test-1','assigned_condition':'audio','selected_label':'Annoyed','correct':False},
        {'test_id':'test-1','assigned_condition':'text','selected_label':'Sarcastic','correct':True},
        {'test_id':'test-1','assigned_condition':'text','selected_label':'Pleased','correct':False},
    ]
    summary = await results('test-1', x_management_token=MANAGEMENT_TOKEN, db=db)
    labels = ['Sarcastic','Pleased','Sad','Angry']

    def previous_python_group(condition):
        rows = [row for row in db.heardit_votes.rows if row['assigned_condition'] == condition]
        n = len(rows)
        correct = sum(row['correct'] for row in rows)
        return {
            'n':n,
            'correct':correct,
            'rate':correct / n if n else None,
            'interval':wilson(correct, n),
            'distribution':{label:sum(row['selected_label'].casefold() == label.casefold() for row in rows) for label in labels},
        }

    audio = previous_python_group('audio')
    text = previous_python_group('text')
    expected = {
        'id':'test-1',
        'intended_label':'Sarcastic',
        'labels':labels,
        'total':4,
        'audio':audio,
        'text':text,
        'voice_lift':audio['rate'] - text['rate'],
        'preliminary':True,
        'interpretation':'Exploratory randomized sample; this difference is not proof of a universal voice effect.',
    }
    assert summary == expected


@pytest.mark.asyncio
async def test_public_product_stats_only_expose_aggregate_counts():
    db = FakeDB()
    db.heardit_votes.rows = [
        {'test_id':'test-1','assigned_condition':'audio','selected_label':'Sarcastic','correct':True},
        {'test_id':'test-1','assigned_condition':'text','selected_label':'Sad','correct':False},
    ]
    result = await public_product_stats(db)
    assert result == {'published_tests':1,'tests_with_responses':1,'listener_responses':2}
    assert not {'sentence','intended_label','direction','assigned_condition'} & result.keys()
