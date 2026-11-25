"""Knowledge target configuration: revision defaultRefs skip git validation."""

from __future__ import annotations

import pytest

from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.errors import AppError, ErrorCode
from app.service.evolution.targets import (
    EvolutionTargetService,
    EvolutionTargetWrite,
)
from tests.m10_02_potential_support import WORKSPACE_A, Harness


class ExplodingGitRemote:
    """Fail the test if a knowledge target ever touches a git remote."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Reject any git validation call."""
        del repo_url, ref
        raise AssertionError("knowledge target must not run git validation")

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Reject any git tag read."""
        del repo_url
        raise AssertionError("knowledge target must not read git tags")


def knowledge_write(
    *,
    name: str,
    default_ref: str,
) -> EvolutionTargetWrite:
    """Build one knowledge target write with a valid generic URL."""
    return EvolutionTargetWrite(
        object_type="knowledge",
        object_name=name,
        repo_url="https://example.invalid/knowledge.git",
        sub_dir="knowledge",
        default_ref=default_ref,
        validation_project_id="validation",
        test_project_id="test",
        primary_metric_key="resolved_rate",
        enabled=True,
    )


async def test_knowledge_target_skips_git_validation_and_versions(harness: Harness) -> None:
    """A digest defaultRef is stored and versions returns [] without git."""
    service = EvolutionTargetService(
        EvolutionTargetRepository(harness.database),
        ExplodingGitRemote(),
    )
    revision = "digest:" + "a" * 64

    created = await service.create(
        knowledge_write(name="Runbook", default_ref=revision),
        workspace_id=WORKSPACE_A,
        created_by=None,
    )
    versions = await service.versions(created.id, workspace_ids=(WORKSPACE_A,))

    assert created.object_type == "knowledge"
    assert created.default_ref == revision
    assert versions.versions == []
    assert versions.default_ref == revision


@pytest.mark.parametrize(
    "default_ref",
    [
        "tag:release-7",
        "digest:" + "b" * 64,
        "provider:kb/runbook",
        "plain-revision",
    ],
)
async def test_knowledge_default_ref_accepts_normalized_revisions(
    harness: Harness,
    default_ref: str,
) -> None:
    """Knowledge defaultRef is a revision, not a git-ref-shaped string."""
    service = EvolutionTargetService(
        EvolutionTargetRepository(harness.database),
        ExplodingGitRemote(),
    )

    created = await service.create(
        knowledge_write(name=f"doc-{default_ref[:8]}", default_ref=default_ref),
        workspace_id=WORKSPACE_A,
        created_by=None,
    )

    assert created.default_ref == default_ref


@pytest.mark.parametrize(
    "default_ref",
    ["digest:bad value", "digest:../escape", "digest:foo@{", "digest:trailing/"],
)
async def test_knowledge_default_ref_still_rejects_unsafe_values(
    harness: Harness,
    default_ref: str,
) -> None:
    """Relaxing the git-ref regex must not admit traversal or whitespace."""
    service = EvolutionTargetService(
        EvolutionTargetRepository(harness.database),
        ExplodingGitRemote(),
    )

    with pytest.raises(AppError) as raised:
        await service.create(
            knowledge_write(name="unsafe-doc", default_ref=default_ref),
            workspace_id=WORKSPACE_A,
            created_by=None,
        )

    assert raised.value.code is ErrorCode.REPO_INVALID
