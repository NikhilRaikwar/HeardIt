import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.fish_tts import FishTTSService, audio_cache_key


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
