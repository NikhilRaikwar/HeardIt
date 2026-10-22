import asyncio
import hashlib
import json
import random
import httpx
from app.core.config import Settings
from app.core.errors import AppError

def audio_cache_key(text: str, model: str, voice_id: str | None, language: str, settings: dict | None = None):
    payload = {'text': ' '.join(text.split()), 'model': model, 'voice_id': voice_id or '', 'language': language, 'format': 'mp3', 'settings': settings or {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def is_audio(data: bytes):
    return len(data) >= 100 and (data[:3] == b'ID3' or (data[0] == 255 and data[1] & 224 == 224))

class FishTTSService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, sleep=asyncio.sleep):
        self.settings, self.client, self.sleep = settings, client, sleep
        self.semaphore = asyncio.Semaphore(settings.fish_concurrency)

    async def generate(self, text: str, language: str, voice_id: str | None = None):
        if not self.settings.fish_api_key.get_secret_value():
            raise AppError(503, 'fish_not_configured', 'Set FISH_API_KEY on the backend to generate speech. No substitute audio will be generated.')
        if not text.strip() or len(text) > 1500 or language not in ('en', 'hi'):
            raise AppError(422, 'invalid_speech_input', 'Speech requires English or Hindi text between 1 and 1,500 characters.')
        body = {'text': text, 'format': 'mp3'}
        if voice_id:
            body['reference_id'] = voice_id
        headers = {'Authorization': f'Bearer {self.settings.fish_api_key.get_secret_value()}', 'model': self.settings.fish_tts_model, 'Content-Type': 'application/json'}
        async with self.semaphore:
            client = self.client or httpx.AsyncClient(timeout=self.settings.fish_timeout)
            try:
                for attempt in range(3):
                    try:
                        response = await client.post('https://api.fish.audio/v1/tts', json=body, headers=headers)
                        if response.status_code in (401, 403):
                            raise AppError(502, 'fish_authentication_failed', 'Fish rejected the API key or model access. Check the server credentials.')
                        if response.status_code == 402:
                            raise AppError(502, 'fish_quota_unavailable', 'Fish reports that quota is unavailable for this account/model.')
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt == 2:
                                raise AppError(503, 'fish_rate_limited' if response.status_code == 429 else 'fish_unavailable', 'Fish is rate limited or unavailable. Retry this failed node later.')
                            await self.sleep((2 ** attempt) + random.uniform(0, .5))
                            continue
                        if response.status_code >= 400:
                            raise AppError(502, 'fish_invalid_request', 'Fish could not synthesize this node. Check its text and configured voice.')
                        content_type = response.headers.get('content-type', '').split(';')[0].lower()
                        if content_type not in ('audio/mpeg', 'audio/mp3', 'application/octet-stream') or not is_audio(response.content) or len(response.content) > 20 * 1024 * 1024:
                            raise AppError(502, 'fish_invalid_audio', 'Fish returned an empty or invalid MP3 response.')
                        return response.content
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt == 2:
                            raise AppError(503, 'fish_timeout', 'Speech generation timed out. Retry the failed node.')
                        await self.sleep((2 ** attempt) + random.uniform(0, .5))
            finally:
                if self.client is None:
                    await client.aclose()
