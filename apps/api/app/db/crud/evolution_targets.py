"""Persistence and aggregate reads for workspace-scoped target configuration."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import delete, distinct, func, insert, select, update
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import agents, bad_cases, evolution_targets
from app.db.models.evolution import evolution_runs
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.utils.ids import new_id
from app.utils.time import now_shanghai

ACTIVE_RUN_STATUSES = ("preparing", "running", "blocked")

EvolutionObjectType = Literal["skill", "agent", "knowledge"]
"""Every object kind a target configuration and the matcher accept."""


@dataclass(frozen=True, slots=True)
class EvolutionTargetRecord:
    """One configurable skill or agent target."""

    id: str
    object_type: EvolutionObjectType
    object_name: str
    repo_url: str
    sub_dir: str
    default_ref: str
    validation_project_id: str
    test_project_id: str
    enabled: bool
    workspace_id: str = DEFAULT_WORKSPACE_ID


@dataclass(frozen=True, slots=True)
class ModelUsageRecord:
    """Aggregated use of one normalized Agent model."""

    model: str
    session_count: int
    agent_count: int


class EvolutionTargetConflict(Exception):
    """The object type/name pair is already configured in this workspace."""


class EvolutionTargetInUse(Exception):
    """The target still has an active evolution run."""


def _scoped(statement: Any, workspace_ids: Sequence[str] | None) -> Any:
    """Apply the optional visible-workspace filter to one target statement."""
    if workspace_ids is None:
        return statement
    return statement.where(evolution_targets.c.workspace_id.in_(workspace_ids))


def _record(row: RowMapping) -> EvolutionTargetRecord:
    """Translate one target row into an immutable boundary record."""
    workspace_id = row["workspace_id"]
    return EvolutionTargetRecord(
        id=row["id"],
        object_type=cast(EvolutionObjectType, row["object_type"]),
        object_name=row["object_name"],
        repo_url=row["repo_url"],
        sub_dir=row["sub_dir"],
        default_ref=row["default_ref"],
        validation_project_id=row["validation_project_id"],
        test_project_id=row["test_project_id"],
        enabled=bool(row["enabled"]),
        workspace_id=(str(workspace_id) if workspace_id is not None else DEFAULT_WORKSPACE_ID),
    )


class EvolutionTargetRepository:
    """Read and write target configuration through one database boundary."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to the application database."""
        self._database = database

    async def list(
        self,
        *,
        enabled_only: bool = False,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return targets in stable display order, optionally scoped to spaces."""
        statement = select(evolution_targets)
        if enabled_only:
            statement = statement.where(evolution_targets.c.enabled.is_(True))
        statement = _scoped(statement, workspace_ids).order_by(
            evolution_targets.c.object_type,
            evolution_targets.c.object_name,
            evolution_targets.c.workspace_id,
            evolution_targets.c.id,
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_record(row) for row in rows)

    async def get(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Return one target by stable identifier inside the optional space scope."""
        statement = _scoped(
            select(evolution_targets).where(evolution_targets.c.id == target_id),
            workspace_ids,
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _record(row) if row is not None else None

    async def find(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Return one target for an object pair inside the optional space scope."""
        rows = await self.find_all(
            object_type,
            object_name,
            workspace_ids=workspace_ids,
        )
        return rows[0] if rows else None

    async def find_all(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return every configured pair match, ordered by workspace and id."""
        statement = _scoped(
            select(evolution_targets).where(
                evolution_targets.c.object_type == object_type,
                evolution_targets.c.object_name == object_name,
            ),
            workspace_ids,
        ).order_by(evolution_targets.c.workspace_id, evolution_targets.c.id)
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_record(row) for row in rows)

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert one configured target and surface only the stable conflict type."""
        target_id = new_id()
        now = now_shanghai()
        workspace_id = str(values.get("workspace_id", DEFAULT_WORKSPACE_ID))
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(evolution_targets).values(
                        id=target_id,
                        workspace_id=workspace_id,
                        object_type=values["object_type"],
                        object_name=values["object_name"],
                        repo_url=values["repo_url"],
                        sub_dir=values["sub_dir"],
                        default_ref=values["default_ref"],
                        validation_project_id=values["validation_project_id"],
                        test_project_id=values["test_project_id"],
                        enabled=values["enabled"],
                        created_by=values.get("created_by"),
                        created_at=now,
                        updated_at=now,
                    ),
                )
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                raise EvolutionTargetConflict from exc
        created = await self.get(target_id)
        if created is None:
            raise RuntimeError("created evolution target disappeared")
        return created

    async def update(
        self,
        target_id: str,
        values: Mapping[str, object],
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Replace the editable fields of one target inside the optional space scope."""
        statement = _scoped(
            update(evolution_targets).where(evolution_targets.c.id == target_id),
            workspace_ids,
        ).values(
            object_type=values["object_type"],
            object_name=values["object_name"],
            repo_url=values["repo_url"],
            sub_dir=values["sub_dir"],
            default_ref=values["default_ref"],
            validation_project_id=values["validation_project_id"],
            test_project_id=values["test_project_id"],
            enabled=values["enabled"],
            updated_at=now_shanghai(),
        )
        async with self._database.transaction() as session:
            try:
                result = cast(CursorResult[object], await session.execute(statement))
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                raise EvolutionTargetConflict from exc
        if result.rowcount != 1:
            raise LookupError("evolution target not found")
        updated = await self.get(target_id)
        if updated is None:
            raise RuntimeError("updated evolution target disappeared")
        return updated

    async def delete(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> bool:
        """Delete an unused target under one row-locked transaction."""
        async with self._database.transaction() as session:
            locked_statement = _scoped(
                select(evolution_targets.c.id).where(
                    evolution_targets.c.id == target_id,
                ),
                workspace_ids,
            )
            locked = (
                await session.execute(locked_statement.with_for_update())
            ).scalar_one_or_none()
            if locked is None:
                return False
            active_count = (
                await session.execute(
                    select(func.count())
                    .select_from(evolution_runs)
                    .where(
                        evolution_runs.c.target_config_id == target_id,
                        evolution_runs.c.status.in_(ACTIVE_RUN_STATUSES),
                    ),
                )
            ).scalar_one()
            if int(active_count) > 0:
                raise EvolutionTargetInUse
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

    async def list_models(
        self,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[ModelUsageRecord, ...]:
        """Aggregate model usage from normalized Agent rows in the given spaces."""
        session_count = func.count(distinct(agents.c.root_session_id))
        agent_count = func.count(agents.c.id)
        statement = select(
            agents.c.model,
            session_count.label("session_count"),
            agent_count.label("agent_count"),
        ).where(
            agents.c.model.is_not(None),
            func.trim(agents.c.model) != "",
        )
        if workspace_ids is not None:
            scoped_sessions = select(bad_cases.c.bad_case_session_id).where(
                bad_cases.c.workspace_id.in_(workspace_ids),
            )
            statement = statement.where(agents.c.root_session_id.in_(scoped_sessions))
        statement = statement.group_by(agents.c.model).order_by(
            session_count.desc(),
            agent_count.desc(),
            agents.c.model,
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
