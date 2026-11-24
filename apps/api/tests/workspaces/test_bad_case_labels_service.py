"""Atomic workspace label replacement behavior."""

import pytest
from fastapi import FastAPI
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models.domain import (
    bad_cases,
    workspace_bad_case_labels,
    workspace_bad_cases,
)
from app.utils.time import now_shanghai
from tests.workspaces.helpers import insert_workspace


async def test_reconciliation_rolls_back_rules_and_assignments_together(
    workspace_client: tuple[FastAPI, object],
) -> None:
    """A failed association rebuild cannot publish the replacement rule set."""
    app, _client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Atomic labels")
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id="atomic-case",
                workspace_id="ws-default",
                bad_case_session_id="session-atomic",
                bad_case_type="self",
                object_name="review",
                object_type="skill",
                title="Atomic",
                bad_case_description="Atomic replacement fixture.",
                catalog_label="new-label",
                created_at=now,
                updated_at=now,
            ),
        )
        await session.execute(
            insert(workspace_bad_case_labels).values(
                workspace_id=workspace_id,
                label="old-label",
                created_at=now,
                updated_at=now,
            ),
        )
        await session.execute(
            text(
                """
                CREATE TRIGGER reject_catalog_assignment
                BEFORE INSERT ON workspace_bad_cases
                WHEN NEW.assignment_source = 'catalog_label'
                BEGIN
                  SELECT RAISE(ABORT, 'reconciliation failed');
                END
                """,
            ),
        )

    with pytest.raises(IntegrityError):
        await app.state.bad_case_labels.replace(workspace_id, ["new-label"])

    async with database.session() as session:
        labels = (
            (
                await session.execute(
                    select(workspace_bad_case_labels.c.label).where(
                        workspace_bad_case_labels.c.workspace_id == workspace_id,
                    ),
                )
            )
            .scalars()
            .all()
        )
        assignments = (
            (
                await session.execute(
                    select(workspace_bad_cases.c.bad_case_id).where(
                        workspace_bad_cases.c.workspace_id == workspace_id,
                    ),
                )
            )
            .scalars()
            .all()
        )

    assert labels == ["old-label"]
    assert assignments == []
