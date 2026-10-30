"""Strict models and protocol for the upstream bad-case catalog query."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BadCaseItem(BaseModel):
    """One upstream bad case shaped like the local bad_cases columns."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    bad_case_id: int = Field(ge=0)
    bad_case_session_id: str = Field(min_length=1, max_length=36)
    bad_case_type: str = Field(min_length=1, max_length=16)
    object_name: str = Field(min_length=1, max_length=128)
    object_type: str = Field(min_length=1, max_length=16)
    object_version: str | None = Field(default=None, max_length=64)
    bad_case_agent_id: str | None = Field(default=None, max_length=64)
    title: str = Field(alias="bad_case_title", min_length=1, max_length=255)
    description: str = Field(alias="bad_case_description")
    meta_data: dict[str, Any] | None = None
    source: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Reject naive timestamps while allowing absent optional values."""
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value


class BadCasePage(BaseModel):
    """One validated page; the page itself proves cursor and size invariants."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    items: tuple[BadCaseItem, ...]

    @model_validator(mode="after")
    def consistent(self) -> BadCasePage:
        """Reject oversized, unsorted, duplicated, or impossible pages."""
        if len(self.items) > self.limit:
            raise ValueError("items exceed the requested limit")
        ids = [item.bad_case_id for item in self.items]
        if ids != sorted(ids):
            raise ValueError("items must be sorted by bad_case_id")
        if len(set(ids)) != len(ids):
            raise ValueError("items must not repeat bad_case_id")
        if self.total < len(self.items):
            raise ValueError("total must cover the returned items")
        return self


class BadCaseCatalogSource(Protocol):
    """Read-only paginated source used by the catalog sync service."""

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Return one page of bad cases with id greater than ``after_id``."""

    async def close(self) -> None:
        """Release owned HTTP resources."""
