"""Durable evolution event history and pagination records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

EVOLUTION_RUN_EVENT_METADATA = MetaData()

evolution_run_events = Table(
    "evolution_run_events",
    EVOLUTION_RUN_EVENT_METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column(
        "run_id",
        String(36),
        ForeignKey("evolution_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("event_type", String(48), nullable=False),
    Column("level", String(8), nullable=False),
    Column("stage", String(32), nullable=False),
    Column("step_index", Integer, nullable=True),
    Column("cluster_id", String(64), nullable=True),
    Column("evolution_round_id", String(36), nullable=True),
    Column("job_id", String(36), nullable=True),
    Column("message", String(512), nullable=False),
    Column("payload", JSON, nullable=True),
    Column("error_type", String(128), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("error_detail", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("run_id", "seq", name="uq_evolution_run_events_run_seq"),
    Index(
        "ix_evolution_run_events_run_created",
        "run_id",
        "created_at",
    ),
    Index("ix_evolution_run_events_event_type", "event_type"),
    Index("ix_evolution_run_events_level", "level"),
    Index("ix_evolution_run_events_cluster_id", "cluster_id"),
)


@dataclass(frozen=True, slots=True)
class RunEventRecord:
    """One persisted event mapped into a database-neutral boundary record."""

    run_id: str
    seq: int
    event_type: str
    level: str
    stage: str
    step_index: int | None
    cluster_id: str | None
    round_id: str | None
    job_id: str | None
    message: str
    payload: dict[str, Any] | None
    error_type: str | None
    error_message: str | None
    error_detail: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RunEventPageRecord:
    """One stable event page plus whether another matching row exists."""

    items: tuple[RunEventRecord, ...]
    has_more: bool
