from functools import lru_cache
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(REPO_ROOT / '.env'), str(API_ROOT / '.env')), extra='ignore')
    environment: str = Field('development', alias='HEARDIT_ENV')
    mongo_uri: str = Field('mongodb://127.0.0.1:27017', alias='MONGODB_URI')
    mongo_database: str = Field('heardit', alias='MONGODB_DATABASE')
    allowed_origins: str = Field('http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001', alias='HEARDIT_ALLOWED_ORIGINS')
    fish_api_key: SecretStr = Field(SecretStr(''), alias='FISH_API_KEY')
    fish_tts_model: Literal['s2.1-pro-free'] = Field('s2.1-pro-free', alias='FISH_TTS_MODEL')
    fish_default_voice_id: str | None = Field(None, alias='FISH_DEFAULT_VOICE_ID')
    fish_concurrency: int = Field(2, ge=1, le=5, alias='FISH_CONCURRENCY')
    fish_timeout: float = Field(90, ge=1, le=300, alias='FISH_TIMEOUT_SECONDS')
    aiml_api_key: SecretStr = Field(SecretStr(''), alias='AIML_API_KEY')
    aiml_model: str = Field('gpt-4o-mini', alias='AIML_MODEL')
    aiml_base_url: str = Field('https://api.aimlapi.com/v1', alias='AIML_BASE_URL')

    @property
    def origins(self):
        return [value.strip() for value in self.allowed_origins.split(',') if value.strip()]

@lru_cache
def get_settings():
    return Settings()
