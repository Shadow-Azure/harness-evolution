"""Dialect-neutral durable job audit table and record."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

from app.utils.time import as_shanghai

JOB_METADATA = MetaData()

job_runs = Table(
    "job_runs",
    JOB_METADATA,
    Column("id", String(36), primary_key=True),
    Column("kind", String(32), nullable=False),
    Column("ref_id", String(64), nullable=True),
    Column("status", String(16), nullable=False),
    Column("progress", Float, nullable=False),
    Column("executor", String(16), nullable=False),
    Column("external_job_id", String(128), nullable=True),
    Column("attempt", Integer, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("result", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column(
        "created_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_job_runs_status", "status"),
    Index("ix_job_runs_ref_id", "ref_id"),
)
Index(
    "ix_job_runs_kind_created_at",
    job_runs.c.kind,
    job_runs.c.created_at.desc(),
)

sync_lock = Table(
    "sync_lock",
    JOB_METADATA,
    Column("name", String(32), primary_key=True),
    Column(
        "job_id",
        String(36),
        ForeignKey("job_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("owner", String(64), nullable=False),
    Column("acquired_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("ix_sync_lock_expires_at", "expires_at"),
)


@dataclass(frozen=True, slots=True)
class JobRunRecord:
    """One durable job row with its queued/running/terminal audit fields."""

    id: str
    kind: str
    ref_id: str | None
    status: str
    progress: float
    executor: str
    external_job_id: str | None
    attempt: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SyncLockRecord:
    """One durable single-flight lock row."""

    name: str
    job_id: str
    owner: str
    acquired_at: datetime
    expires_at: datetime


def record_from_row(row: Any) -> JobRunRecord:
    """Translate one SQLAlchemy row mapping into an immutable job record."""
    started_at = row["started_at"]
    finished_at = row["finished_at"]
    return JobRunRecord(
        id=row["id"],
        kind=row["kind"],
        ref_id=row["ref_id"],
        status=row["status"],
        progress=float(row["progress"]),
        executor=row["executor"],
        external_job_id=row["external_job_id"],
        attempt=int(row["attempt"]),
        payload=dict(row["payload"]),
        result=dict(row["result"]) if row["result"] is not None else None,
        error=row["error"],
        created_by=row["created_by"],
        created_at=as_shanghai(row["created_at"]),
        started_at=as_shanghai(started_at) if started_at is not None else None,
        finished_at=as_shanghai(finished_at) if finished_at is not None else None,
        updated_at=as_shanghai(row["updated_at"]),
    )
