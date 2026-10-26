"""Persistence and aggregate reads for evolution target configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import delete, distinct, func, insert, select, update
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.models.domain import agents, evolution_targets
from app.db.models.evolution import evolution_runs
from app.utils.ids import new_id
from app.utils.time import now_shanghai

ACTIVE_RUN_STATUSES = ("preparing", "running", "blocked")


@dataclass(frozen=True, slots=True)
class EvolutionTargetRecord:
    """One configurable skill or agent target."""

    id: str
    object_type: Literal["skill", "agent"]
    object_name: str
    repo_url: str
    sub_dir: str
    default_ref: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class ModelUsageRecord:
    """Aggregated use of one normalized Agent model."""

    model: str
    session_count: int
    agent_count: int


class EvolutionTargetConflict(Exception):
    """The object type/name pair is already configured."""


def _record(row: RowMapping) -> EvolutionTargetRecord:
    """Translate one target row into an immutable boundary record."""
    return EvolutionTargetRecord(
        id=row["id"],
        object_type=cast(Literal["skill", "agent"], row["object_type"]),
        object_name=row["object_name"],
        repo_url=row["repo_url"],
        sub_dir=row["sub_dir"],
        default_ref=row["default_ref"],
        enabled=bool(row["enabled"]),
    )


class EvolutionTargetRepository:
    """Read and write target configuration through one database boundary."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to the application database."""
        self._database = database

    async def list(self, *, enabled_only: bool = False) -> tuple[EvolutionTargetRecord, ...]:
        """Return all targets, or only enabled targets, in stable display order."""
        statement = select(evolution_targets)
        if enabled_only:
            statement = statement.where(evolution_targets.c.enabled.is_(True))
        statement = statement.order_by(
            evolution_targets.c.object_type,
            evolution_targets.c.object_name,
            evolution_targets.c.id,
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_record(row) for row in rows)

    async def get(self, target_id: str) -> EvolutionTargetRecord | None:
        """Return one target by stable identifier."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(evolution_targets).where(
                            evolution_targets.c.id == target_id,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _record(row) if row is not None else None

    async def find(
        self,
        object_type: str,
        object_name: str,
    ) -> EvolutionTargetRecord | None:
        """Return the target for one object type/name pair."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(evolution_targets).where(
                            evolution_targets.c.object_type == object_type,
                            evolution_targets.c.object_name == object_name,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _record(row) if row is not None else None

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert one configured target and surface only the stable conflict type."""
        target_id = new_id()
        now = now_shanghai()
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(evolution_targets).values(
                        id=target_id,
                        object_type=values["object_type"],
                        object_name=values["object_name"],
                        repo_url=values["repo_url"],
                        sub_dir=values["sub_dir"],
                        default_ref=values["default_ref"],
                        enabled=values["enabled"],
                        created_by=values.get("created_by"),
                        created_at=now,
                        updated_at=now,
                    ),
                )
            except IntegrityError as exc:
                raise EvolutionTargetConflict from exc
        created = await self.get(target_id)
        if created is None:
            raise RuntimeError("created evolution target disappeared")
        return created

    async def update(
        self,
        target_id: str,
        values: Mapping[str, object],
    ) -> EvolutionTargetRecord:
        """Replace the editable fields of one existing target."""
        async with self._database.transaction() as session:
            try:
                result = cast(
                    CursorResult[object],
                    await session.execute(
                        update(evolution_targets)
                        .where(evolution_targets.c.id == target_id)
                        .values(
                            object_type=values["object_type"],
                            object_name=values["object_name"],
                            repo_url=values["repo_url"],
                            sub_dir=values["sub_dir"],
                            default_ref=values["default_ref"],
                            enabled=values["enabled"],
                            updated_at=now_shanghai(),
                        ),
                    ),
                )
            except IntegrityError as exc:
                raise EvolutionTargetConflict from exc
        if result.rowcount != 1:
            raise LookupError("evolution target not found")
        updated = await self.get(target_id)
        if updated is None:
            raise RuntimeError("updated evolution target disappeared")
        return updated

    async def delete(self, target_id: str) -> bool:
        """Delete one target and report whether a row existed."""
        async with self._database.transaction() as session:
            result = cast(
                CursorResult[object],
                await session.execute(
                    delete(evolution_targets).where(
                        evolution_targets.c.id == target_id,
                    ),
                ),
            )
        return result.rowcount == 1

    async def has_active_runs(self, target_id: str) -> bool:
        """Return whether a non-terminal run references this target."""
        async with self._database.session() as session:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(evolution_runs)
                    .where(
                        evolution_runs.c.target_config_id == target_id,
                        evolution_runs.c.status.in_(ACTIVE_RUN_STATUSES),
                    ),
                )
            ).scalar_one()
        return int(count) > 0

    async def list_models(self) -> tuple[ModelUsageRecord, ...]:
        """Aggregate distinct-session and Agent-row counts from normalized models."""
        session_count = func.count(distinct(agents.c.root_session_id))
        agent_count = func.count(agents.c.id)
        statement = (
            select(
                agents.c.model,
                session_count.label("session_count"),
                agent_count.label("agent_count"),
            )
            .where(
                agents.c.model.is_not(None),
                func.trim(agents.c.model) != "",
            )
            .group_by(agents.c.model)
            .order_by(
                session_count.desc(),
                agent_count.desc(),
                agents.c.model,
            )
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(
            ModelUsageRecord(
                model=row["model"],
                session_count=int(row["session_count"]),
                agent_count=int(row["agent_count"]),
            )
            for row in rows
        )
