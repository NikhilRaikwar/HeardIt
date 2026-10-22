"""The provider boundary: only validated, size-limited MP3 bytes leave here."""

import asyncio
import hashlib
import json
import random
from functools import lru_cache

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError

MAX_AUDIO_BYTES = 4 * 1024 * 1024
FISH_TTS_URL = 'https://api.fish.audio/v1/tts'
DEFAULT_VOICE_CONFIGURATION = 'fish-account-default-v1'


def canonical_speech_text(direction: str, sentence: str) -> str:
    """Use the same normalization in synthesis, hashing, storage and publish."""
    return ' '.join(f'{direction} {sentence}'.split())


def voice_configuration(voice_id: str | None) -> str:
    return voice_id or DEFAULT_VOICE_CONFIGURATION


def audio_cache_key(text: str, model: str, voice_id: str | None, language: str, settings: dict | None = None) -> str:
    """Retained for callers that already provide a complete speech input."""
    payload = {'text': ' '.join(text.split()), 'model': model, 'voice_id': voice_id or '', 'language': language, 'format': 'mp3', 'settings': settings or {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def synthesis_cache_key(direction: str, sentence: str, model: str, voice_id: str | None = None) -> str:
    """Hash the actual fixed MVP provider configuration, including its cue."""
    payload = {
        'model': model,
        'input_text': canonical_speech_text(direction, sentence),
        'direction': ' '.join(direction.split()),
        'voice': voice_configuration(voice_id),
        'output': {'format': 'mp3'},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def is_audio(data: bytes) -> bool:
    return len(data) >= 100 and (data[:3] == b'ID3' or (data[0] == 255 and data[1] & 224 == 224))


class FishTTSService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, sleep=asyncio.sleep):
        self.settings, self.client, self.sleep = settings, client, sleep
        self.semaphore = asyncio.Semaphore(settings.fish_concurrency)

    async def _read_audio(self, response: httpx.Response) -> bytes:
        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        if content_type not in ('audio/mpeg', 'audio/mp3', 'application/octet-stream'):
            raise AppError(502, 'fish_invalid_audio', 'Fish Audio did not return a playable MP3. Please try again.')
        audio = bytearray()
        async for chunk in response.aiter_bytes():
            if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                raise AppError(502, 'fish_invalid_audio', 'Fish Audio returned a clip larger than the 4 MB storage limit.')
            audio.extend(chunk)
        if not is_audio(audio):
            raise AppError(502, 'fish_invalid_audio', 'Fish Audio returned an empty or invalid MP3. Please try again.')
        return bytes(audio)

    async def generate(self, text: str, language: str = 'en', voice_id: str | None = None) -> bytes:
        if not self.settings.fish_api_key.get_secret_value():
            raise AppError(503, 'fish_not_configured', 'Set FISH_API_KEY on the backend to generate speech. No substitute audio will be generated.')
        # Public routes enforce 180-character sentence / 120-character cue limits.
        text = ' '.join(text.split())
        if not text or len(text) > 1500 or language not in ('en', 'hi'):
            raise AppError(422, 'invalid_speech_input', 'Speech requires English or Hindi text between 1 and 1,500 characters.')
        body = {'text': text, 'format': 'mp3'}
        selected_voice = voice_id or self.settings.fish_default_voice_id
        if selected_voice:
            body['reference_id'] = selected_voice
        headers = {
            'Authorization': f'Bearer {self.settings.fish_api_key.get_secret_value()}',
            'model': self.settings.fish_tts_model,
            'Content-Type': 'application/json',
        }
        async with self.semaphore:
            client = self.client or httpx.AsyncClient(timeout=self.settings.fish_timeout)
            try:
                for attempt in range(3):
                    try:
                        # Streaming stops an unexpectedly large upstream response
                        # before it can exceed the application's storage limit.
                        async with client.stream('POST', FISH_TTS_URL, json=body, headers=headers) as response:
                            if response.status_code in (401, 403):
                                raise AppError(502, 'fish_authentication_failed', 'Fish Audio rejected the configured key or model access. Check the server credentials.')
                            if response.status_code == 402:
                                raise AppError(503, 'fish_quota_unavailable', 'Fish Audio reports that account quota is unavailable. Try again after quota is restored.')
                            if response.status_code == 429 or response.status_code >= 500:
                                if attempt == 2:
                                    if response.status_code == 429:
                                        raise AppError(429, 'fish_rate_limited', 'Fish Audio is rate limiting requests. Try again shortly.')
                                    raise AppError(503, 'fish_unavailable', 'Fish Audio is temporarily unavailable. Try again shortly.')
                            elif not 200 <= response.status_code < 300:
                                raise AppError(502, 'fish_invalid_request', 'Fish Audio could not synthesize this clip. Check its text and configured voice.')
                            else:
                                return await self._read_audio(response)
                    except httpx.TimeoutException as error:
                        if attempt == 2:
                            raise AppError(503, 'fish_timeout', 'Fish Audio took too long. Please try again.') from error
                    except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
                        if attempt == 2:
                            raise AppError(503, 'fish_unavailable', 'Fish Audio could not be reached. Try again shortly.') from error
                    await self.sleep((2 ** attempt) + random.uniform(0, .5))
            finally:
                if self.client is None:
                    await client.aclose()
        raise AppError(503, 'fish_unavailable', 'Fish Audio could not generate this clip. Please try again.')


@lru_cache
def get_fish_service() -> FishTTSService:
    """FastAPI dependency; reuse the semaphore across this worker's requests."""
    return FishTTSService(get_settings())
