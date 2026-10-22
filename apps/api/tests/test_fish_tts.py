import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.fish_tts import (
    MAX_AUDIO_BYTES,
    FishTTSService,
    audio_cache_key,
    canonical_speech_text,
    get_fish_service,
    synthesis_cache_key,
)


def configured_settings():
    settings = get_settings().model_copy(update={
        'fish_api_key': SecretStr('test-only-key'),
        'fish_tts_model': 's2.1-pro-free',
        'fish_default_voice_id': None,
        'fish_concurrency': 1,
        'fish_timeout': 2,
    })
    return settings


@pytest.mark.asyncio
async def test_fish_request_uses_free_model_header_and_validates_mp3():
    observed = {}
    mp3 = b'ID3' + bytes(128)

    async def handler(request):
        observed['url'] = str(request.url)
        observed['model'] = request.headers['model']
        observed['auth'] = request.headers['authorization']
        observed['body'] = __import__('json').loads(request.content)
        return httpx.Response(200, headers={'Content-Type': 'audio/mpeg'}, content=mp3)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FishTTSService(configured_settings(), client=client).generate('Hello there.', 'en', 'voice-1')

    assert result == mp3
    assert observed == {
        'url': 'https://api.fish.audio/v1/tts',
        'model': 's2.1-pro-free',
        'auth': 'Bearer test-only-key',
        'body': {'text': 'Hello there.', 'format': 'mp3', 'reference_id': 'voice-1'},
    }


@pytest.mark.asyncio
async def test_authentication_errors_are_not_retried():
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={'error': 'unauthorized'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as error:
            await FishTTSService(configured_settings(), client=client, sleep=lambda _seconds: None).generate('Hello.', 'en')
    assert error.value.code == 'fish_authentication_failed'
    assert calls == 1


@pytest.mark.asyncio
async def test_bad_input_and_invalid_audio_fail_without_substitution():
    async def handler(_request):
        return httpx.Response(200, headers={'Content-Type': 'audio/mpeg'}, content=b'')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = FishTTSService(configured_settings(), client=client)
        with pytest.raises(AppError, match='Speech requires'):
            await service.generate('  ', 'en')
        with pytest.raises(AppError) as error:
            await service.generate('Hello.', 'en')
    assert error.value.code == 'fish_invalid_audio'


def test_audio_cache_key_normalizes_whitespace_but_includes_voice_model_and_language():
    baseline = audio_cache_key('Hello   there', 's2.1-pro-free', 'voice-a', 'en')
    assert baseline == audio_cache_key('Hello there', 's2.1-pro-free', 'voice-a', 'en')
    assert baseline != audio_cache_key('Hello there', 's2.1-pro-free', 'voice-b', 'en')
    assert baseline != audio_cache_key('Hello there', 's2.1-pro-free', 'voice-a', 'hi')
    assert baseline != audio_cache_key('Hello there', 'different-model', 'voice-a', 'en')


@pytest.mark.asyncio
@pytest.mark.parametrize(('provider_status', 'status', 'code', 'attempts'), [
    (401, 502, 'fish_authentication_failed', 1),
    (403, 502, 'fish_authentication_failed', 1),
    (402, 503, 'fish_quota_unavailable', 1),
    (429, 429, 'fish_rate_limited', 3),
    (500, 503, 'fish_unavailable', 3),
    (503, 503, 'fish_unavailable', 3),
    (422, 502, 'fish_invalid_request', 1),
    (302, 502, 'fish_invalid_request', 1),
])
async def test_provider_failures_are_friendly_and_retries_are_bounded(provider_status, status, code, attempts):
    requests, waits = [], []

    async def handler(request):
        requests.append(request)
        return httpx.Response(provider_status, json={'provider_error': 'must not reach client'})

    async def sleep(seconds):
        waits.append(seconds)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as error:
            await FishTTSService(configured_settings(), client=client, sleep=sleep).generate('Hello.', 'en')
    assert (error.value.status, error.value.code) == (status, code)
    assert 'must not reach client' not in error.value.message
    assert len(requests) == attempts
    assert len(waits) == attempts - 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('failure', 'code'), [
    (httpx.ReadTimeout, 'fish_timeout'),
    (httpx.ConnectError, 'fish_unavailable'),
    (httpx.RemoteProtocolError, 'fish_unavailable'),
])
async def test_network_errors_retry_at_most_twice(failure, code):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise failure('provider details must stay private', request=request)

    async def no_wait(_seconds):
        pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as error:
            await FishTTSService(configured_settings(), client=client, sleep=no_wait).generate('Hello.')
    assert error.value.status == 503
    assert error.value.code == code
    assert calls == 3


@pytest.mark.asyncio
async def test_transient_failure_can_recover_without_changing_provider():
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, headers={'content-type': 'audio/mpeg'}, content=b'ID3' + bytes(128))

    async def no_wait(_seconds):
        pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FishTTSService(configured_settings(), client=client, sleep=no_wait).generate('Hello.')
    assert result.startswith(b'ID3')
    assert calls == ['https://api.fish.audio/v1/tts'] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize(('content_type', 'data'), [
    ('application/json', b'ID3' + bytes(128)),
    ('audio/mpeg', b'{"error":"not an mp3"}' + bytes(128)),
    ('audio/mpeg', b'ID3' + bytes(MAX_AUDIO_BYTES)),
], ids=['wrong-content-type', 'not-an-mp3', 'too-large'])
async def test_invalid_or_oversize_provider_output_is_rejected(content_type, data):
    async def handler(_request):
        return httpx.Response(200, headers={'content-type': content_type}, content=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as error:
            await FishTTSService(configured_settings(), client=client).generate('Hello.')
    assert error.value.code == 'fish_invalid_audio'


@pytest.mark.asyncio
async def test_empty_key_and_oversize_input_do_not_call_fish():
    calls = []

    async def handler(request):
        calls.append(request)
        raise AssertionError('provider must not be called')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        missing_key = configured_settings().model_copy(update={'fish_api_key': SecretStr('')})
        with pytest.raises(AppError) as error:
            await FishTTSService(missing_key, client=client).generate('Hello.')
        assert error.value.code == 'fish_not_configured'
        with pytest.raises(AppError) as error:
            await FishTTSService(configured_settings(), client=client).generate('x' * 1501)
        assert error.value.code == 'invalid_speech_input'
    assert calls == []


@pytest.mark.asyncio
async def test_configured_voice_and_canonical_text_are_sent():
    observed = {}

    async def handler(request):
        observed.update(__import__('json').loads(request.content))
        return httpx.Response(200, headers={'content-type': 'audio/mpeg'}, content=b'ID3' + bytes(128))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        settings = configured_settings().model_copy(update={'fish_default_voice_id': 'fixed-voice'})
        await FishTTSService(settings, client=client).generate(' [curious]  Hello\nthere. ')
    assert observed == {'text': '[curious] Hello there.', 'format': 'mp3', 'reference_id': 'fixed-voice'}


def test_canonical_speech_and_cache_use_one_normalization():
    assert canonical_speech_text(' [curious,  gentle]\n', ' Hello\tthere. ') == '[curious, gentle] Hello there.'
    canonical = synthesis_cache_key('[curious, gentle]', 'Hello there.', 's2.1-pro-free')
    assert canonical == synthesis_cache_key(' [curious,  gentle]\n', ' Hello\tthere. ', 's2.1-pro-free')
    assert canonical != synthesis_cache_key('[annoyed]', 'Hello there.', 's2.1-pro-free')
    assert canonical != synthesis_cache_key('[curious, gentle]', 'Hello there.', 'another-model')
    assert canonical != synthesis_cache_key('[curious, gentle]', 'Hello there.', 's2.1-pro-free', 'fixed-voice')


def test_dependency_reuses_the_service_semaphore():
    get_fish_service.cache_clear()
    assert get_fish_service() is get_fish_service()
    get_fish_service.cache_clear()
