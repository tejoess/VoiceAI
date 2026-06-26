"""Agent API schemas with registry-backed validation."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.capabilities import DEFAULT_CAPABILITIES
from app.data.languages import DEFAULT_LANGUAGE
from app.data.speaking_styles import DEFAULT_STYLE
from app.data.tones import DEFAULT_TONE
from app.data.voices import DEFAULT_VOICE
from app.services import registry


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    is_active: bool = True

    system_prompt: str = Field("", max_length=8000)
    greeting: str = Field("", max_length=2000)
    fallback_message: str = Field("", max_length=2000)

    voice_id: str = DEFAULT_VOICE
    primary_language: str = DEFAULT_LANGUAGE
    languages: list[str] = Field(default_factory=lambda: [DEFAULT_LANGUAGE])
    tone: str = DEFAULT_TONE
    speaking_style: str = DEFAULT_STYLE
    capabilities: list[str] = Field(default_factory=lambda: list(DEFAULT_CAPABILITIES))

    llm_temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(300, ge=32, le=4096)
    stt_provider: str = "deepgram"

    webhook_url: str | None = Field(None, max_length=500)
    settings: dict = Field(default_factory=dict)

    @field_validator("stt_provider")
    @classmethod
    def _stt_provider_ok(cls, v: str) -> str:
        if v not in ("deepgram", "sarvam"):
            raise ValueError(f"unknown stt_provider: {v}")
        return v

    @field_validator("voice_id")
    @classmethod
    def _voice_ok(cls, v: str) -> str:
        if not registry.validate_voice(v):
            raise ValueError(f"unknown voice_id: {v}")
        return v

    @field_validator("primary_language")
    @classmethod
    def _lang_ok(cls, v: str) -> str:
        if not registry.validate_language(v):
            raise ValueError(f"unsupported language: {v}")
        return v

    @field_validator("tone")
    @classmethod
    def _tone_ok(cls, v: str) -> str:
        if not registry.validate_tone(v):
            raise ValueError(f"unknown tone: {v}")
        return v

    @field_validator("speaking_style")
    @classmethod
    def _style_ok(cls, v: str) -> str:
        if not registry.validate_style(v):
            raise ValueError(f"unknown speaking_style: {v}")
        return v

    @field_validator("languages")
    @classmethod
    def _langs_ok(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if not registry.validate_language(c)]
        if bad:
            raise ValueError(f"unsupported languages: {bad}")
        return v

    @field_validator("capabilities")
    @classmethod
    def _caps_ok(cls, v: list[str]) -> list[str]:
        bad = registry.validate_capabilities(v)
        if bad:
            raise ValueError(f"unknown capabilities: {bad}")
        return v

    @model_validator(mode="after")
    def _primary_in_languages(self) -> "AgentBase":
        if self.primary_language not in self.languages:
            self.languages = [self.primary_language, *self.languages]
        return self


class AgentCreate(AgentBase):
    business_id: uuid.UUID | None = None


class AgentUpdate(BaseModel):
    """All fields optional for PATCH semantics."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    system_prompt: str | None = None
    greeting: str | None = None
    fallback_message: str | None = None
    voice_id: str | None = None
    primary_language: str | None = None
    languages: list[str] | None = None
    tone: str | None = None
    speaking_style: str | None = None
    capabilities: list[str] | None = None
    llm_temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=32, le=4096)
    stt_provider: str | None = None
    webhook_url: str | None = None
    settings: dict | None = None

    @field_validator("stt_provider")
    @classmethod
    def _stt_provider_ok(cls, v):
        if v is not None and v not in ("deepgram", "sarvam"):
            raise ValueError(f"unknown stt_provider: {v}")
        return v

    @field_validator("voice_id")
    @classmethod
    def _voice_ok(cls, v):
        if v is not None and not registry.validate_voice(v):
            raise ValueError(f"unknown voice_id: {v}")
        return v

    @field_validator("primary_language")
    @classmethod
    def _lang_ok(cls, v):
        if v is not None and not registry.validate_language(v):
            raise ValueError(f"unsupported language: {v}")
        return v

    @field_validator("tone")
    @classmethod
    def _tone_ok(cls, v):
        if v is not None and not registry.validate_tone(v):
            raise ValueError(f"unknown tone: {v}")
        return v

    @field_validator("speaking_style")
    @classmethod
    def _style_ok(cls, v):
        if v is not None and not registry.validate_style(v):
            raise ValueError(f"unknown speaking_style: {v}")
        return v

    @field_validator("languages")
    @classmethod
    def _langs_ok(cls, v):
        if v is not None:
            bad = [c for c in v if not registry.validate_language(c)]
            if bad:
                raise ValueError(f"unsupported languages: {bad}")
        return v

    @field_validator("capabilities")
    @classmethod
    def _caps_ok(cls, v):
        if v is not None:
            bad = registry.validate_capabilities(v)
            if bad:
                raise ValueError(f"unknown capabilities: {bad}")
        return v


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("voice_id", mode="before")
    @classmethod
    def _voice_ok(cls, v: str) -> str:  # type: ignore[override]
        # When reading from the DB, silently coerce stale/renamed voice IDs to
        # the current default rather than failing the whole response.
        if not registry.validate_voice(v):
            return DEFAULT_VOICE
        return v
