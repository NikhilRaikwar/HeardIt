from functools import lru_cache
from typing import Literal
from pydantic import Field, SecretStr, model_validator
import secrets
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
    signing_secret: SecretStr = Field(SecretStr(''), alias='HEARDIT_SIGNING_SECRET')
    assignment_token_max_age: int = Field(604800, ge=60, alias='HEARDIT_ASSIGNMENT_TOKEN_MAX_AGE_SECONDS')
    trust_proxy: bool = Field(False, alias='HEARDIT_TRUST_PROXY')
    publish_ip_hourly: int = Field(20, ge=1, alias='HEARDIT_PUBLISH_IP_HOURLY')
    publish_audio_hourly: int = Field(20, ge=1, alias='HEARDIT_PUBLISH_AUDIO_HOURLY')
    assignment_ip_minute: int = Field(60, ge=1, alias='HEARDIT_ASSIGNMENT_IP_MINUTE')
    assignment_test_minute: int = Field(300, ge=1, alias='HEARDIT_ASSIGNMENT_TEST_MINUTE')
    vote_ip_minute: int = Field(30, ge=1, alias='HEARDIT_VOTE_IP_MINUTE')
    vote_test_minute: int = Field(120, ge=1, alias='HEARDIT_VOTE_TEST_MINUTE')
    tests_daily_cap: int = Field(500, ge=1, alias='HEARDIT_TESTS_DAILY_CAP')
    votes_per_test_daily_cap: int = Field(10000, ge=1, alias='HEARDIT_VOTES_PER_TEST_DAILY_CAP')
    captcha_enabled: bool = Field(False, alias='HEARDIT_CAPTCHA_ENABLED')
    turnstile_secret: SecretStr = Field(SecretStr(''), alias='HEARDIT_TURNSTILE_SECRET')
    admin_key: SecretStr = Field(SecretStr(''), alias='ADMIN_KEY')

    @model_validator(mode='after')
    def require_production_signing_secret(self):
        value = self.signing_secret.get_secret_value()
        if self.environment == 'production' and len(value) < 32:
            raise ValueError('HEARDIT_SIGNING_SECRET must contain at least 32 characters in production.')
        admin_key = self.admin_key.get_secret_value()
        if admin_key and len(admin_key) < 32:
            raise ValueError('ADMIN_KEY must contain at least 32 characters when configured.')
        if not value:
            # Local development only: tokens intentionally expire across API restarts.
            self.signing_secret = SecretStr(secrets.token_urlsafe(48))
        return self

    @property
    def origins(self):
        return [value.strip() for value in self.allowed_origins.split(',') if value.strip()]

@lru_cache
def get_settings():
    return Settings()
