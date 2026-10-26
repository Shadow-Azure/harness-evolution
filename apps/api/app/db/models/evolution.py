"""Dialect-neutral persistence tables and records for the evolution loop."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, cast

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
)

from app.utils.time import as_shanghai

EVOLUTION_METADATA = MetaData()

evolution_runs = Table(
    "evolution_runs",
    EVOLUTION_METADATA,
    Column("id", String(36), primary_key=True),
    Column("title", String(255), nullable=False),
    Column("mode", String(16), nullable=False),
    Column("engine_key", String(64), nullable=False),
    Column("eval_config", JSON, nullable=False),
    Column(
        "target_config_id",
        String(36),
        ForeignKey("evolution_targets.id"),
        nullable=False,
    ),
    Column("target_type", String(16), nullable=False),
    Column("target_name", String(128), nullable=False),
    Column("target_version", String(64), nullable=False),
    Column("repo_url", String(1024), nullable=False),
    Column("sub_dir", String(512), nullable=False),
    Column("repo_path", String(1024), nullable=True),
    Column("base_ref", String(128), nullable=True),
    Column("base_commit", String(40), nullable=True),
    Column("branch_name", String(128), nullable=True),
    Column("workspace_path", String(1024), nullable=True),
    Column(
        "remote_name",
        String(64),
        nullable=False,
        server_default="origin",
    ),
    Column(
        "push_status",
        String(16),
        nullable=False,
        server_default="pending",
    ),
    Column("pushed_at", DateTime(timezone=True), nullable=True),
    Column("push_error", Text, nullable=True),
    Column("window_from", Date, nullable=True),
    Column("window_to", Date, nullable=True),
    Column("models", JSON, nullable=True),
    Column("status", String(16), nullable=False, server_default="preparing"),
    Column("blocked_stage", String(16), nullable=True),
    Column("retry_attempts", Integer, nullable=False, server_default="0"),
    Column("next_retry_at", DateTime(timezone=True), nullable=True),
    Column("eval_status", String(16), nullable=False, server_default="pending"),
    Column("error_stage", String(32), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("error_at", DateTime(timezone=True), nullable=True),
    Column("progress_unit", Integer, nullable=False, server_default="0"),
    Column("stats", JSON, nullable=True),
    Column(
        "created_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Index("ix_evolution_runs_status", "status"),
    Index("ix_evolution_runs_push_status", "push_status"),
    Index(
        "ix_evolution_runs_status_next_retry",
        "status",
        "next_retry_at",
    ),
    Index(
        "ix_evolution_runs_target_version",
        "target_type",
        "target_name",
        "target_version",
    ),
    Index("ix_evolution_runs_target_config", "target_config_id"),
)
Index("ix_evolution_runs_created_at", evolution_runs.c.created_at.desc())

probe_clusters = Table(
    "probe_clusters",
    EVOLUTION_METADATA,
    Column("probe_cluster_id", String(64), primary_key=True),
    Column(
        "run_id",
        String(36),
        ForeignKey("evolution_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("probe_cluster_description", Text, nullable=False),
    Column("probe_cluster_type", String(16), nullable=False),
    Column("confidence", Float, nullable=True),
    Column("impact", Float, nullable=False),
    Column("severity", Float, nullable=True),
    Column("rank", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("run_id", "seq", name="uq_probe_clusters_run_seq"),
    Index("ix_probe_clusters_run", "run_id"),
    Index("ix_probe_clusters_run_rank", "run_id", "rank"),
)

probe_cluster_probes = Table(
    "probe_cluster_probes",
    EVOLUTION_METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column(
        "probe_cluster_id",
        String(64),
        ForeignKey("probe_clusters.probe_cluster_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "probe_id",
        String(64),
        ForeignKey("probe_reports.probe_id"),
        nullable=False,
    ),
    UniqueConstraint(
        "probe_cluster_id",
        "probe_id",
        name="uq_probe_cluster_probes_pair",
    ),
    Index("ix_probe_cluster_probes_probe", "probe_id"),
)

evolution_rounds = Table(
    "evolution_rounds",
    EVOLUTION_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "run_id",
        String(36),
        ForeignKey("evolution_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "probe_cluster_id",
        String(64),
        ForeignKey("probe_clusters.probe_cluster_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("patch", JSON, nullable=True),
    Column("candidate_ref", String(255), nullable=True),
    Column("candidate_commit", String(40), nullable=True),
    Column("candidate_message", Text, nullable=True),
    Column(
        "push_status",
        String(16),
        nullable=False,
        server_default="pending",
    ),
    Column("push_attempts", Integer, nullable=False, server_default="0"),
    Column("pushed_at", DateTime(timezone=True), nullable=True),
    Column("push_error", Text, nullable=True),
    Column("eval_external_id", String(128), nullable=True),
    Column("eval_status", String(16), nullable=False, server_default="pending"),
    Column("eval_attempts", Integer, nullable=False, server_default="0"),
    Column("eval_next_poll_at", DateTime(timezone=True), nullable=True),
    Column("eval_started_at", DateTime(timezone=True), nullable=True),
    Column("eval_finished_at", DateTime(timezone=True), nullable=True),
    Column("eval_current", Float, nullable=True),
    Column("eval_candidate", Float, nullable=True),
    Column("eval_result", JSON, nullable=True),
    Column("eval_error", Text, nullable=True),
    Column("accepted", Boolean, nullable=False, server_default=false()),
    Column("commit_hash", String(40), nullable=True),
    Column("commit_message", Text, nullable=True),
    UniqueConstraint("run_id", "seq", name="uq_evolution_rounds_run_seq"),
    Index("ix_evolution_rounds_cluster", "probe_cluster_id"),
    Index("ix_evolution_rounds_run_status", "run_id", "status"),
    Index(
        "ix_evolution_rounds_eval_poll",
        "eval_status",
        "eval_next_poll_at",
    ),
)

evolution_finals = Table(
    "evolution_finals",
    EVOLUTION_METADATA,
    Column(
        "run_id",
        String(36),
        ForeignKey("evolution_runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("best_version", String(64), nullable=False),
    Column("verdict", Boolean, nullable=False),
    Column("best_score", Float, nullable=False),
    Column("init_score", Float, nullable=False),
    Column("metrics", JSON, nullable=False),
)


@dataclass(frozen=True, slots=True)
class EvolutionRunRecord:
    """One durable run with configuration snapshots and current state."""

    id: str
    title: str
    mode: str
    engine_key: str
    eval_config: dict[str, Any]
    target_config_id: str
    target_type: str
    target_name: str
    target_version: str
    repo_url: str
    sub_dir: str
    repo_path: str | None
    base_ref: str | None
    base_commit: str | None
    branch_name: str | None
    workspace_path: str | None
    remote_name: str
    push_status: str
    pushed_at: datetime | None
    push_error: str | None
    window_from: date | None
    window_to: date | None
    models: list[str]
    status: str
    blocked_stage: str | None
    retry_attempts: int
    next_retry_at: datetime | None
    eval_status: str
    error_stage: str | None
    error_message: str | None
    error_at: datetime | None
    progress_unit: int
    stats: dict[str, Any]
    created_by: str | None
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProbeClusterRecord:
    """One run-scoped placeholder cluster."""

    probe_cluster_id: str
    run_id: str
    seq: int
    probe_cluster_description: str
    probe_cluster_type: Literal["model", "prompt", "error"]
    confidence: float | None
    impact: float
    severity: float | None
    rank: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProbeClusterLinkRecord:
    """One ordered cluster-to-probe link."""

    id: int
    probe_cluster_id: str
    probe_id: str


@dataclass(frozen=True, slots=True)
class EvolutionRoundRecord:
    """One durable candidate/evaluation round."""

    id: str
    run_id: str
    probe_cluster_id: str
    seq: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    patch: dict[str, Any] | None
    candidate_ref: str | None
    candidate_commit: str | None
    candidate_message: str | None
    push_status: str
    push_attempts: int
    pushed_at: datetime | None
    push_error: str | None
    eval_external_id: str | None
    eval_status: str
    eval_attempts: int
    eval_next_poll_at: datetime | None
    eval_started_at: datetime | None
    eval_finished_at: datetime | None
    eval_current: float | None
    eval_candidate: float | None
    eval_result: dict[str, Any] | None
    eval_error: str | None
    accepted: bool
    commit_hash: str | None
    commit_message: str | None


@dataclass(frozen=True, slots=True)
class EvolutionFinalRecord:
    """One run's terminal evaluation summary."""

    run_id: str
    best_version: str
    verdict: bool
    best_score: float
    init_score: float
    metrics: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ClusterWrite:
    """Database-neutral cluster payload used by repository writes."""

    type: Literal["model", "prompt", "error"]
    description: str
    probes: tuple[str, ...]


def _optional_text(value: object) -> str | None:
    """Return an optional string without coercing unrelated database values."""
    return value if isinstance(value, str) and value else None


def _required_text(value: object) -> str:
    """Return a required string or fail on a malformed selected row."""
    if isinstance(value, str):
        return value
    raise TypeError("expected a database string")


def _json_dict(value: object) -> dict[str, Any]:
    """Copy one JSON object and degrade absent data to an empty object."""
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_json_dict(value: object) -> dict[str, Any] | None:
    """Copy an optional JSON object without accepting arbitrary scalar values."""
    return dict(value) if isinstance(value, Mapping) else None


def _json_strings(value: object) -> list[str]:
    """Copy a JSON string array and reject malformed scalar rows."""
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


def _json_dicts(value: object) -> list[dict[str, Any]]:
    """Copy a JSON object array and reject malformed scalar rows."""
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _timestamp(value: object) -> datetime:
    """Require a timestamp and normalize it to Asia/Shanghai."""
    if not isinstance(value, datetime):
        raise TypeError("expected a database timestamp")
    return as_shanghai(value)


def _optional_timestamp(value: object) -> datetime | None:
    """Normalize an optional timestamp to Asia/Shanghai."""
    return _timestamp(value) if value is not None else None


def _optional_date(value: object) -> date | None:
    """Return an optional date without accepting timestamps."""
    return value if isinstance(value, date) and not isinstance(value, datetime) else None


def record_from_evolution_run(row: Mapping[str, Any]) -> EvolutionRunRecord:
    """Translate one run row mapping into an immutable boundary record."""
    return EvolutionRunRecord(
        id=_required_text(row["id"]),
        title=_required_text(row["title"]),
        mode=_required_text(row["mode"]),
        engine_key=_required_text(row["engine_key"]),
        eval_config=_json_dict(row["eval_config"]),
        target_config_id=_required_text(row["target_config_id"]),
        target_type=_required_text(row["target_type"]),
        target_name=_required_text(row["target_name"]),
        target_version=_required_text(row["target_version"]),
        repo_url=_required_text(row["repo_url"]),
        sub_dir=_required_text(row["sub_dir"]),
        repo_path=_optional_text(row["repo_path"]),
        base_ref=_optional_text(row["base_ref"]),
        base_commit=_optional_text(row["base_commit"]),
        branch_name=_optional_text(row["branch_name"]),
        workspace_path=_optional_text(row["workspace_path"]),
        remote_name=_required_text(row["remote_name"]),
        push_status=_required_text(row["push_status"]),
        pushed_at=_optional_timestamp(row["pushed_at"]),
        push_error=_optional_text(row["push_error"]),
        window_from=_optional_date(row["window_from"]),
        window_to=_optional_date(row["window_to"]),
        models=_json_strings(row["models"]),
        status=_required_text(row["status"]),
        blocked_stage=_optional_text(row["blocked_stage"]),
        retry_attempts=int(row["retry_attempts"]),
        next_retry_at=_optional_timestamp(row["next_retry_at"]),
        eval_status=_required_text(row["eval_status"]),
        error_stage=_optional_text(row["error_stage"]),
        error_message=_optional_text(row["error_message"]),
        error_at=_optional_timestamp(row["error_at"]),
        progress_unit=int(row["progress_unit"]),
        stats=_json_dict(row["stats"]),
        created_by=_optional_text(row["created_by"]),
        created_at=_timestamp(row["created_at"]),
        finished_at=_optional_timestamp(row["finished_at"]),
    )


def record_from_probe_cluster(row: Mapping[str, Any]) -> ProbeClusterRecord:
    """Translate one cluster row mapping into an immutable boundary record."""
    return ProbeClusterRecord(
        probe_cluster_id=_required_text(row["probe_cluster_id"]),
        run_id=_required_text(row["run_id"]),
        seq=int(row["seq"]),
        probe_cluster_description=_required_text(row["probe_cluster_description"]),
        probe_cluster_type=cast(
            Literal["model", "prompt", "error"],
            _required_text(row["probe_cluster_type"]),
        ),
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        impact=float(row["impact"]),
        severity=float(row["severity"]) if row["severity"] is not None else None,
        rank=int(row["rank"]) if row["rank"] is not None else None,
        created_at=_timestamp(row["created_at"]),
    )


def record_from_probe_cluster_link(
    row: Mapping[str, Any],
) -> ProbeClusterLinkRecord:
    """Translate one cluster link row mapping into a boundary record."""
    return ProbeClusterLinkRecord(
        id=int(row["id"]),
        probe_cluster_id=_required_text(row["probe_cluster_id"]),
        probe_id=_required_text(row["probe_id"]),
    )


def record_from_evolution_round(row: Mapping[str, Any]) -> EvolutionRoundRecord:
    """Translate one round row mapping into an immutable boundary record."""
    return EvolutionRoundRecord(
        id=_required_text(row["id"]),
        run_id=_required_text(row["run_id"]),
        probe_cluster_id=_required_text(row["probe_cluster_id"]),
        seq=int(row["seq"]),
        status=_required_text(row["status"]),
        started_at=_optional_timestamp(row["started_at"]),
        finished_at=_optional_timestamp(row["finished_at"]),
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        error_message=_optional_text(row["error_message"]),
        patch=_optional_json_dict(row["patch"]),
        candidate_ref=_optional_text(row["candidate_ref"]),
        candidate_commit=_optional_text(row["candidate_commit"]),
        candidate_message=_optional_text(row["candidate_message"]),
        push_status=_required_text(row["push_status"]),
        push_attempts=int(row["push_attempts"]),
        pushed_at=_optional_timestamp(row["pushed_at"]),
        push_error=_optional_text(row["push_error"]),
        eval_external_id=_optional_text(row["eval_external_id"]),
        eval_status=_required_text(row["eval_status"]),
        eval_attempts=int(row["eval_attempts"]),
        eval_next_poll_at=_optional_timestamp(row["eval_next_poll_at"]),
        eval_started_at=_optional_timestamp(row["eval_started_at"]),
        eval_finished_at=_optional_timestamp(row["eval_finished_at"]),
        eval_current=(float(row["eval_current"]) if row["eval_current"] is not None else None),
        eval_candidate=(
            float(row["eval_candidate"]) if row["eval_candidate"] is not None else None
        ),
        eval_result=_optional_json_dict(row["eval_result"]),
        eval_error=_optional_text(row["eval_error"]),
        accepted=bool(row["accepted"]),
        commit_hash=_optional_text(row["commit_hash"]),
        commit_message=_optional_text(row["commit_message"]),
    )


def record_from_evolution_final(row: Mapping[str, Any]) -> EvolutionFinalRecord:
    """Translate one terminal evaluation row mapping into a boundary record."""
    return EvolutionFinalRecord(
        run_id=_required_text(row["run_id"]),
        best_version=_required_text(row["best_version"]),
        verdict=bool(row["verdict"]),
        best_score=float(row["best_score"]),
        init_score=float(row["init_score"]),
        metrics=_json_dicts(row["metrics"]),
    )
