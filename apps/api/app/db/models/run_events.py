"""Read-only projection of the evolution event history owned by m5-08."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
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
    Column("run_id", String(36), nullable=False),
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
