"""Workspace badcase label configuration rules."""

from collections.abc import Sequence

from app.db.crud.workspace_bad_case_labels import (
    WorkspaceBadCaseLabelRecord,
    WorkspaceBadCaseLabelRepository,
)
from app.errors import AppError, ErrorCode
from app.service.workspaces.schemas import WorkspaceBadCaseLabelConfiguration


class WorkspaceBadCaseLabelService:
    """Expose sorted label resources over atomic repository operations."""

    def __init__(self, repository: WorkspaceBadCaseLabelRepository) -> None:
        """Bind workspace label behavior to its persistence boundary."""
        self._repository = repository

    async def get(self, workspace_id: str) -> WorkspaceBadCaseLabelConfiguration:
        """Return one workspace's complete label configuration."""
        return self._to_configuration(await self._repository.get(workspace_id))

    async def replace(
        self,
        workspace_id: str,
        labels: Sequence[str],
    ) -> WorkspaceBadCaseLabelConfiguration:
        """Atomically replace a workspace's rules and historical assignments."""
        normalized = tuple(sorted(labels))
        record = await self._repository.replace(workspace_id, normalized)
        if record is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="workspace was not found",
            )
        return self._to_configuration(record)

    @staticmethod
    def _to_configuration(
        record: WorkspaceBadCaseLabelRecord,
    ) -> WorkspaceBadCaseLabelConfiguration:
        """Translate a repository record without leaking persistence types."""
        return WorkspaceBadCaseLabelConfiguration(
            items=list(record.items),
            assigned_bad_case_count=record.assigned_bad_case_count,
        )
