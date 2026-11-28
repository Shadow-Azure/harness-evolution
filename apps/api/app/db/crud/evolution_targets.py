"""Persistence and aggregate reads for workspace-scoped target configuration."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import and_, delete, distinct, func, insert, or_, select, update
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.candidate_sources import normalize_sources, validate_sources
from app.db.crud.integrity import is_unique_violation
from app.db.crud.read_scope import scoped_case_ids
from app.db.models.domain import (
    agents,
    attribution_skill_packages,
    bad_cases,
    evolution_target_members,
    evolution_targets,
)
from app.db.models.evolution import evolution_runs
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.errors import AppError, ErrorCode
from app.utils.ids import new_id
from app.utils.time import now_shanghai

ACTIVE_RUN_STATUSES = ("preparing", "running", "blocked")

EvolutionObjectType = Literal["skill", "agent", "knowledge"]
"""Every object kind a target configuration and the matcher accept."""


@dataclass(frozen=True, slots=True)
class EvolutionTargetMemberRecord:
    """One skill or agent member of a multi-member evolution target."""

    id: str
    target_id: str
    workspace_id: str
    seq: int
    object_type: EvolutionObjectType
    object_name: str
    sub_dir: str
    match_by_name: bool = False
    definition: dict[str, Any] | None = None


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
    attribution_package_id: str | None = None
    attribution_skill_name: str | None = None
    attribution_failures: int = 0
    attribution_error: str | None = None
    attribution_will_retry: bool = False
    attribution_generation: str | None = None
    attribution_snapshot: dict[str, Any] | None = None
    candidate_policy: dict[str, Any] | None = None
    primary_metric_key: str = ""
    members: tuple[EvolutionTargetMemberRecord, ...] = ()
    match_by_name: bool = False

    @property
    def definition(self) -> dict[str, str] | None:
        return (self.attribution_snapshot or {}).get("definition")

    def member_for(self, object_type: str, object_name: str) -> EvolutionTargetMemberRecord | None:
        """Return the member matching one object identity, if any."""
        return next(
            (
                member
                for member in self.members
                if member.object_type == object_type and member.object_name == object_name
            ),
            None,
        )

    @property
    def member_objects(self) -> tuple[EvolutionTargetMemberRecord, ...]:
        """Return configured members or one synthesized legacy member."""
        if self.members:
            return self.members
        return (
            EvolutionTargetMemberRecord(
                id="",
                target_id=self.id,
                workspace_id=self.workspace_id,
                seq=0,
                object_type=self.object_type,
                object_name=self.object_name,
                sub_dir=self.sub_dir,
                definition=self.definition,
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelUsageRecord:
    """Aggregated use of one normalized Agent model."""

    model: str
    session_count: int
    agent_count: int


class EvolutionTargetConflict(Exception):
    """The object type/name pair is already configured in this workspace."""


class EvolutionTargetMemberConflict(Exception):
    """One member already belongs to another configuration in this workspace."""


class EvolutionTargetInUse(Exception):
    """The target still has an active evolution run."""


def _scoped(statement: Any, workspace_ids: Sequence[str] | None) -> Any:
    """Apply the optional visible-workspace filter to one target statement."""
    if workspace_ids is None:
        return statement
    return statement.where(evolution_targets.c.workspace_id.in_(workspace_ids))


def _member_record(row: RowMapping) -> EvolutionTargetMemberRecord:
    """Translate one member row into an immutable boundary record."""
    definition = row["definition"]
    return EvolutionTargetMemberRecord(
        id=str(row["id"]),
        target_id=str(row["target_id"]),
        workspace_id=str(row["workspace_id"]),
        seq=int(row["seq"]),
        object_type=cast(EvolutionObjectType, row["object_type"]),
        object_name=str(row["object_name"]),
        sub_dir=str(row["sub_dir"]),
        match_by_name=bool(row.get("match_by_name", False)),
        definition=dict(definition) if isinstance(definition, Mapping) else None,
    )


def _record(
    row: RowMapping,
    members: Sequence[EvolutionTargetMemberRecord] = (),
) -> EvolutionTargetRecord:
    """Translate one target row and its members into an immutable record.

    Legacy configurations inserted before the member table existed may still
    have only the old object columns. The first member is authoritative once
    present, so reads keep working across the migration window.
    """
    ordered = tuple(members)
    first = ordered[0] if ordered else None
    object_type = row["object_type"] or (first.object_type if first else "skill")
    object_name = row["object_name"] or (first.object_name if first else "")
    sub_dir = row["sub_dir"] or (first.sub_dir if first else ".")
    workspace_id = row["workspace_id"]
    return EvolutionTargetRecord(
        id=row["id"],
        object_type=cast(EvolutionObjectType, object_type),
        object_name=object_name,
        repo_url=row["repo_url"],
        sub_dir=sub_dir,
        default_ref=row["default_ref"],
        validation_project_id=row["validation_project_id"],
        test_project_id=row["test_project_id"],
        primary_metric_key=row["primary_metric_key"],
        candidate_policy=normalize_sources(row["candidate_policy"])
        if row["candidate_policy"]
        else None,
        enabled=bool(row["enabled"]),
        attribution_package_id=row["attribution_package_id"],
        attribution_skill_name=row["attribution_skill_name"],
        attribution_failures=row["attribution_failures"],
        attribution_error=row["attribution_error"],
        attribution_will_retry=row["attribution_due"] is not None,
        attribution_generation=row["attribution_generation"],
        attribution_snapshot=row["attribution_snapshot"],
        workspace_id=(str(workspace_id) if workspace_id is not None else DEFAULT_WORKSPACE_ID),
        members=ordered,
    )


async def _load_members(
    session: Any,
    target_ids: Sequence[str],
) -> dict[str, tuple[EvolutionTargetMemberRecord, ...]]:
    """Batch-load ordered member rows for the requested target ids."""
    if not target_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(evolution_target_members)
                .where(evolution_target_members.c.target_id.in_(tuple(target_ids)))
                .order_by(evolution_target_members.c.target_id, evolution_target_members.c.seq),
            )
        )
        .mappings()
        .all()
    )
    grouped: dict[str, list[EvolutionTargetMemberRecord]] = {}
    for row in rows:
        member = _member_record(row)
        grouped.setdefault(member.target_id, []).append(member)
    return {key: tuple(value) for key, value in grouped.items()}


def _member_values(values: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """Return the normalized member payload, falling back to one legacy object."""
    members = values.get("members")
    if isinstance(members, Sequence) and not isinstance(members, (str, bytes)) and members:
        return tuple(
            cast(Mapping[str, object], member) for member in members if isinstance(member, Mapping)
        )
    return (
        {
            "object_type": values["object_type"],
            "object_name": values["object_name"],
            "sub_dir": values["sub_dir"],
            "match_by_name": bool(values.get("match_by_name", False)),
            "definition": values.get("definition"),
        },
    )


def _member_rows(
    values: Mapping[str, object],
    *,
    target_id: str,
    workspace_id: str,
    now: Any,
) -> list[dict[str, object]]:
    """Build the member rows written in the same transaction as the config."""
    return [
        {
            "id": new_id(),
            "workspace_id": workspace_id,
            "target_id": target_id,
            "seq": seq,
            "object_type": member["object_type"],
            "object_name": member["object_name"],
            "sub_dir": member["sub_dir"],
            "match_by_name": bool(member.get("match_by_name", False)),
            "definition": member.get("definition"),
            "created_at": now,
        }
        for seq, member in enumerate(_member_values(values))
    ]


def _member_signature(values: Mapping[str, object]) -> tuple[tuple[object, ...], ...]:
    """Return the member identity used to decide whether a binding is stale."""
    return tuple(
        (
            member["object_type"],
            member["object_name"],
            member["sub_dir"],
            bool(member.get("match_by_name", False)),
            member.get("definition"),
        )
        for member in _member_values(values)
    )


def _member_unique_violation(exc: IntegrityError) -> bool:
    """Return whether a member identity index caused the unique violation."""
    text = str(exc.orig).lower()
    return "evolution_target_members" in text or "uq_evolution_target_members" in text


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
            members = await _load_members(session, [str(row["id"]) for row in rows])
        return tuple(_record(row, members.get(str(row["id"]), ())) for row in rows)

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
            members = await _load_members(session, [target_id])
        return _record(row, members.get(target_id, ())) if row is not None else None

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
        """Return every configured pair match, ordered by workspace and id.

        New configurations resolve identity through the member table; legacy
        rows that predate the member backfill still match their old columns.
        """
        members = evolution_target_members
        member_match = and_(
            members.c.target_id == evolution_targets.c.id,
            members.c.object_type == object_type,
            members.c.object_name == object_name,
        )
        row_without_members = and_(
            members.c.id.is_(None),
            evolution_targets.c.object_type == object_type,
            evolution_targets.c.object_name == object_name,
        )
        statement = (
            select(evolution_targets)
            .outerjoin(members, members.c.target_id == evolution_targets.c.id)
            .where(or_(member_match, row_without_members))
        )
        statement = _scoped(statement, workspace_ids).order_by(
            evolution_targets.c.workspace_id,
            evolution_targets.c.id,
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
            loaded = await _load_members(session, [str(row["id"]) for row in rows])
        seen: dict[str, EvolutionTargetRecord] = {}
        for row in rows:
            target_id = str(row["id"])
            if target_id not in seen:
                seen[target_id] = _record(row, loaded.get(target_id, ()))
        return tuple(seen.values())

    async def _binding(
        self, session: Any, workspace: str, package: str, enabled: bool, definition: object = None
    ) -> dict[str, Any]:
        name = "attribute-badcases"
        if package != "default-attribute-badcases":
            name = (
                await session.execute(
                    select(attribution_skill_packages.c.skill_name)
                    .where(
                        attribution_skill_packages.c.workspace_id == workspace,
                        attribution_skill_packages.c.id == package,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if name is None:
                raise AppError(
                    status_code=422,
                    code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_INVALID,
                    message="Skill package does not exist in this workspace",
                )
        now = now_shanghai()
        return dict(
            attribution_package_id=package,
            attribution_skill_name=name,
            attribution_generation=new_id(),
            attribution_owner=None,
            attribution_failures=0,
            attribution_error=None,
            attribution_snapshot={"definition": definition} if definition else None,
            attribution_due=now if enabled else None,
            attribution_cutoff=now,
        )

    async def pin_binding_skill(
        self, target: EvolutionTargetRecord, *, skill_key: str, revision: int, content_hash: str
    ) -> dict[str, Any]:
        """Both entrypoints adopt the first Skill frozen for this binding generation."""
        t = evolution_targets.c
        binding = (
            t.id == target.id,
            t.workspace_id == target.workspace_id,
            t.attribution_package_id == target.attribution_package_id,
            t.attribution_generation == target.attribution_generation,
        )
        proposed = {
            **(target.attribution_snapshot or {}),
            "skill": skill_key,
            "skillRevision": revision,
            "hash": content_hash,
        }
        async with self._database.transaction() as session:
            await session.execute(
                update(evolution_targets)
                .where(*binding, t.attribution_snapshot["skill"].as_string().is_(None))
                .values(attribution_snapshot=proposed)
            )
            snapshot = (
                await session.execute(select(t.attribution_snapshot).where(*binding))
            ).scalar_one_or_none()
            if snapshot is None:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.ATTRIBUTION_SKILL_INVALID,
                    message="target binding changed while freezing its attribution Skill",
                )
            return dict(snapshot)

    async def save_policy(
        self, workspace: str, target_id: str, policy: dict[str, Any]
    ) -> dict[str, Any]:
        policy = normalize_sources(policy)
        t = evolution_targets.c
        scope = and_(t.workspace_id == workspace, t.id == target_id)
        async with self._database.transaction() as session:
            row = (
                (await session.execute(select(evolution_targets).where(scope).with_for_update()))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.TARGET_NOT_CONFIGURED,
                    message="target not found",
                )
            previous = row["candidate_policy"]
            if policy == previous:
                return policy
            await validate_sources(session, workspace, policy)
            values = dict(candidate_policy=policy, updated_at=now_shanghai())
            if row["attribution_package_id"] and (
                previous is None or policy != normalize_sources(previous)
            ):
                values.update(
                    await self._binding(
                        session,
                        workspace,
                        row["attribution_package_id"],
                        row["enabled"],
                        (row["attribution_snapshot"] or {}).get("definition"),
                    )
                )
            await session.execute(update(evolution_targets).where(scope).values(**values))
            return policy

    async def bind_package(self, workspace: str, target: str, package: str) -> None:
        async with self._database.transaction() as session:
            table = evolution_targets
            query = table.c.workspace_id == workspace, table.c.id == target
            row = (
                (await session.execute(select(table).where(*query).with_for_update()))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.TARGET_NOT_CONFIGURED,
                    message="target not found",
                )
            if row["attribution_package_id"] != package:
                await session.execute(
                    update(table)
                    .where(*query)
                    .values(
                        **await self._binding(
                            session,
                            workspace,
                            package,
                            row["enabled"],
                            (row["attribution_snapshot"] or {}).get("definition"),
                        )
                    )
                )

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert one configured target and surface only the stable conflict type."""
        target_id = new_id()
        now = now_shanghai()
        workspace_id = str(values.get("workspace_id", DEFAULT_WORKSPACE_ID))
        members = _member_values(values)
        first = members[0]
        async with self._database.transaction() as session:
            try:
                policy = values.get("candidate_policy")
                if isinstance(policy, dict):
                    policy = normalize_sources(policy)
                    await validate_sources(session, workspace_id, policy)
                package = values.get("attribution_package_id", "default-attribute-badcases")
                binding = (
                    await self._binding(
                        session,
                        workspace_id,
                        str(package),
                        bool(values["enabled"]),
                        first.get("definition"),
                    )
                    if package is not None
                    else {}
                )
                await session.execute(
                    insert(evolution_targets).values(
                        **binding,
                        id=target_id,
                        candidate_policy=policy,
                        workspace_id=workspace_id,
                        object_type=first["object_type"],
                        object_name=first["object_name"],
                        repo_url=values["repo_url"],
                        sub_dir=first["sub_dir"],
                        default_ref=values["default_ref"],
                        validation_project_id=values["validation_project_id"],
                        test_project_id=values["test_project_id"],
                        primary_metric_key=values.get("primary_metric_key", ""),
                        enabled=values["enabled"],
                        created_by=values.get("created_by"),
                        created_at=now,
                        updated_at=now,
                    ),
                )
                await session.execute(
                    insert(evolution_target_members),
                    _member_rows(
                        values,
                        target_id=target_id,
                        workspace_id=workspace_id,
                        now=now,
                    ),
                )
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                if _member_unique_violation(exc):
                    raise EvolutionTargetMemberConflict from exc
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
        members = _member_values(values)
        first = members[0]
        statement = _scoped(
            update(evolution_targets).where(evolution_targets.c.id == target_id),
            workspace_ids,
        ).values(
            object_type=first["object_type"],
            object_name=first["object_name"],
            repo_url=values["repo_url"],
            sub_dir=first["sub_dir"],
            default_ref=values["default_ref"],
            validation_project_id=values["validation_project_id"],
            test_project_id=values["test_project_id"],
            primary_metric_key=values.get("primary_metric_key", ""),
            enabled=values["enabled"],
            updated_at=now_shanghai(),
        )
        async with self._database.transaction() as session:
            try:
                existing = (
                    (
                        await session.execute(
                            _scoped(
                                select(evolution_targets).where(
                                    evolution_targets.c.id == target_id
                                ),
                                workspace_ids,
                            ).with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is None:
                    raise LookupError("evolution target not found")
                policy = values.get("candidate_policy")
                policy_changed = False
                if isinstance(policy, dict):
                    policy = normalize_sources(policy)
                    previous = existing["candidate_policy"]
                    policy_changed = previous is None or policy != normalize_sources(previous)
                    if policy != previous:
                        await validate_sources(session, existing["workspace_id"], policy)
                        statement = statement.values(candidate_policy=policy)
                previous_members = await _load_members(session, [target_id])
                changed_members = tuple(
                    (
                        member.object_type,
                        member.object_name,
                        member.sub_dir,
                        member.match_by_name,
                        member.definition,
                    )
                    for member in previous_members.get(target_id, ())
                ) != _member_signature(values)
                package = values.get("attribution_package_id") or existing["attribution_package_id"]
                if not package and first.get("definition"):
                    # A legacy inline Skill remains bound until a package is selected.
                    statement = statement.values(
                        attribution_snapshot={"definition": first["definition"]}
                    )
                if package and (
                    policy_changed
                    or package != existing["attribution_package_id"]
                    or changed_members
                    or any(
                        existing[k] != values[k]
                        for k in (
                            "enabled",
                            "default_ref",
                            "repo_url",
                        )
                    )
                ):
                    statement = statement.values(
                        **await self._binding(
                            session,
                            existing["workspace_id"],
                            str(package),
                            bool(values["enabled"]),
                            first.get("definition"),
                        )
                    )
                elif (
                    existing["enabled"]
                    and existing["attribution_error"]
                    and existing["attribution_due"] is None
                ):
                    # A deliberate save of a failed target resumes the same frozen batch.
                    # Previously completed cases stay linked to its generation.
                    statement = statement.values(
                        attribution_failures=0,
                        attribution_error=None,
                        attribution_due=now_shanghai(),
                    )
                result = cast(CursorResult[object], await session.execute(statement))
                await session.execute(
                    delete(evolution_target_members).where(
                        evolution_target_members.c.target_id == target_id
                    )
                )
                await session.execute(
                    insert(evolution_target_members),
                    _member_rows(
                        values,
                        target_id=target_id,
                        workspace_id=str(existing["workspace_id"]),
                        now=now_shanghai(),
                    ),
                )
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                if _member_unique_violation(exc):
                    raise EvolutionTargetMemberConflict from exc
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
                bad_cases.c.bad_case_id.in_(scoped_case_ids(workspace_ids)),
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
