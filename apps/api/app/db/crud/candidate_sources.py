"""Workspace-scoped queries over canonical bad cases and their assignments."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.models.domain import bad_cases
from app.errors import AppError, ErrorCode
from app.utils.time import as_shanghai


def _name(session: AsyncSession) -> Any:
    column = bad_cases.c.object_name
    return (
        column.collate("utf8mb4_0900_bin") if session.get_bind().dialect.name == "mysql" else column
    )


def _report_label(session: AsyncSession) -> Any:
    """Catalog routing owns catalog_label; direct reports may supply metaData.label."""
    c = bad_cases.c
    raw = c.meta_data["label"].as_string()
    length: Callable[[Any], Any]
    if session.get_bind().dialect.name == "mysql":
        is_text = func.json_type(func.json_extract(c.meta_data, "$.label")) == "STRING"
        length = func.char_length
    else:
        is_text = func.json_type(c.meta_data, "$.label") == "text"
        length = func.length
    valid = and_(
        c.origin == "report",
        is_text,
        length(raw).between(1, 128),
        length(raw) == length(func.trim(raw)),
    )
    return func.coalesce(c.catalog_label, case((valid, raw)))


def _scope(workspace: str) -> Any:
    c = bad_cases.c
    return and_(
        WorkspaceReadScope.for_workspace(workspace).case_condition(),
        c.object_type.in_(("skill", "agent")),
        c.object_name != "",
        c.bad_case_type.in_(("self", "discovery")),
    )


def normalize_sources(policy: dict[str, Any]) -> dict[str, Any]:
    """Keep the first rule for each exact source, report-type set and relation."""
    seen = set()
    rules = []
    for rule in policy["rules"]:
        types = tuple(kind for kind in ("self", "discovery") if kind in rule["types"])
        key = (rule["kind"], rule["name"], types, rule["relation"])
        if key not in seen:
            seen.add(key)
            rules.append({**rule, "types": list(types)})
    return {**policy, "rules": rules}


async def validate_sources(session: AsyncSession, workspace: str, policy: dict[str, Any]) -> None:
    required = {(rule["kind"], rule["name"]) for rule in policy["rules"]}
    if not required:
        return
    name = _name(session)
    found = await session.execute(
        select(bad_cases.c.object_type, name)
        .distinct()
        .where(_scope(workspace), name.in_({item[1] for item in required}))
    )
    if required.difference(tuple(row) for row in found):
        raise AppError(
            status_code=422,
            code=ErrorCode.POLICY_INVALID,
            message="来源对象必须在当前工作区有上报记录",
        )


class CandidateSourcesRepository:
    def __init__(self, database: Database):
        self.database = database

    async def counts(self, workspace: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        c = bad_cases.c
        window = and_(c.created_at >= start, c.created_at < end)
        async with self.database.session() as session:
            name = _name(session)

            def count(kind: str) -> Any:
                return func.sum(case((and_(window, c.bad_case_type == kind), 1), else_=0))

            query = (
                select(
                    c.object_type.label("kind"),
                    name.label("name"),
                    count("self").label("self_count"),
                    count("discovery").label("discovery_count"),
                )
                .where(_scope(workspace))
                .group_by(c.object_type, name)
                .order_by(c.object_type, name)
            )
            return [dict(row) for row in (await session.execute(query)).mappings()]

    async def reports(
        self,
        workspace: str,
        start: datetime,
        end: datetime,
        *,
        kind: str,
        name: str,
        types: Sequence[str],
        labels: Sequence[str],
        unlabelled: bool,
        filter_type: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        c = bad_cases.c
        async with self.database.session() as session:
            scope = and_(
                _scope(workspace),
                c.object_type == kind,
                _name(session) == name,
                c.bad_case_type.in_(types),
                c.created_at >= start,
                c.created_at < end,
            )
            label = _report_label(session)
            counts = (
                await session.execute(
                    select(label, func.count()).where(scope).group_by(label).order_by(label)
                )
            ).all()
            filtered = scope
            if filter_type:
                filtered = and_(filtered, c.bad_case_type == filter_type)
            if labels or unlabelled:
                filtered = and_(
                    filtered,
                    or_(
                        label.in_(labels),
                        label.is_(None) if unlabelled else false(),
                    ),
                )
            total = (
                await session.execute(select(func.count()).select_from(bad_cases).where(filtered))
            ).scalar_one()
            query = (
                select(
                    c.bad_case_id.label("id"),
                    c.title,
                    c.bad_case_type.label("report_type"),
                    label.label("label"),
                    c.created_at,
                )
                .where(filtered)
                .order_by(c.created_at.desc(), c.bad_case_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = (await session.execute(query)).mappings()
            return dict(
                items=[{**row, "created_at": as_shanghai(row["created_at"])} for row in rows],
                labels=[label for label, _ in counts],
                source_total=sum(n for _, n in counts),
                total=total,
            )
