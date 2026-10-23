from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    captcha_token: str | None = Field(default=None, max_length=4096)

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


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participant_id: str = Field(min_length=24, max_length=128)
    captcha_token: str | None = Field(default=None, max_length=4096)


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


class HealthResponse(BaseModel):
    status: Literal['ok']
    database: Literal['mongodb']
    fish_configured: bool
    indexes_ready: bool


class PublicProductStats(BaseModel):
    published_tests: int
    tests_with_responses: int
    listener_responses: int


class ProductEventRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal[
        'landing_viewed', 'create_started', 'ai_suggestion_requested', 'audio_generated',
        'voice_generation_completed', 'test_published', 'test_opened', 'audio_played',
        'vote_submitted', 'results_viewed', 'share_clicked', 'review_opened',
        'share_page_viewed', 'voice_generation_started', 'voice_generation_failed',
    ]
    properties: dict[str, str | bool | int | float] = Field(default_factory=dict, max_length=12)


class ProductEventResponse(BaseModel):
    accepted: Literal[True]


class AdminServerConfirmedStats(BaseModel):
    tests_published: int
    tests_with_responses: int
    votes_accepted: int


class AdminClientReportedStats(BaseModel):
    funnel: dict[str, int]


class AdminStatsResponse(BaseModel):
    server_confirmed: AdminServerConfirmedStats
    client_reported: AdminClientReportedStats


class AudioGenerateResponse(BaseModel):
    audio_id: str
    url: str
    cached: bool
    model: str
    direction: str
    voice: str
    created_at: str


class PublishResponse(BaseModel):
    id: str
    management_token: str
    status: Literal['published']


class CreatorTestResponse(BaseModel):
    id: str
    sentence: str
    intended_label: str
    distractors: list[str]
    direction: str
    model: str
    audio_id: str
    created_at: str
    status: Literal['published']


class TestOption(BaseModel):
    id: str
    label: str
    description: str = ''


class PublicTestResponse(BaseModel):
    id: str
    options: list[TestOption]
    labels: list[str]
    condition: Literal['audio', 'text']
    sentence: str | None = None
    audio_url: str | None = None


class AssignmentResponse(BaseModel):
    condition: Literal['audio', 'text']
    assignment_token: str | None
    creator_preview: bool


class VoteResponse(BaseModel):
    submitted: Literal[True]
    intended_label: str
    correct: bool


class ResultGroup(BaseModel):
    n: int
    correct: int
    rate: float | None
    interval: list[float] | None
    distribution: dict[str, int]


class ResultsResponse(BaseModel):
    id: str
    intended_label: str
    labels: list[str]
    total: int
    audio: ResultGroup
    text: ResultGroup
    voice_lift: float | None
    preliminary: bool
    interpretation: str
