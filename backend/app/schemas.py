from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CreateDiscussion(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    expert_count: int = Field(default=4, ge=2, le=6)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("议题不能为空")
        return value
