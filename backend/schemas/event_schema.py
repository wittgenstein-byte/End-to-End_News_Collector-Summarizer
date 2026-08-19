"""
schemas/event_schema.py
────────────────────────────────────────────────────────────────
SOLID  I — schema สำหรับ anonymous user event tracking
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class EventRecordRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    event_name: str = Field(
        ...,
        validation_alias=AliasChoices("event_name", "event"),
    )
    article_url: str | None = None
    article_title: str | None = None
    source: str | None = None
    category: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    consented: bool = True

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("event name must not be empty")
        return cleaned

    @field_validator("article_url")
    @classmethod
    def validate_article_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if cleaned and not cleaned.startswith(("http://", "https://")):
            raise ValueError("article_url must start with http:// or https://")
        return cleaned

    @property
    def event(self) -> str:
        return self.event_name
