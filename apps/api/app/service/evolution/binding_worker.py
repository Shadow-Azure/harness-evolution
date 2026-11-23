"""Analyze the finite set of workspace cases present when a target was bound."""

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta

from app.db.crud.attributions import AttributionRepository
from app.db.crud.binding_batches import BindingClaim, BindingQueue
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_sync_coordinator import BadCaseRootSyncCoordinator
from app.service.evolution.attribution import (
    AttributionRunner,
    AttributionRunProgress,
    BindingBatch,
)
from app.service.evolution.local_attribution import ENGINE, LocalAttribution
from app.service.evolution.potential import MatchCondition, PotentialMatcher, resolve_policy
from app.service.evolution.target_content import GitDefinitionRef, TargetVersionResolver
from app.utils.time import SHANGHAI, now_shanghai

logger = logging.getLogger(__name__)


class BindingWorker:
    def __init__(
        self,
        queue: BindingQueue,
        acquisition: BadCaseRootSyncCoordinator,
        runtime: LocalAttribution,
        resolver: TargetVersionResolver,
        matcher: PotentialMatcher,
        reports: AttributionRepository,
        runner: AttributionRunner,
    ):
        self.queue = queue
        self.acquisition = acquisition
        self.runtime = runtime
        self.resolver = resolver
        self.matcher = matcher
        self.reports = reports
        self.runner = runner
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop(), name="bound-skill-attribution")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def loop(self) -> None:
        while True:
            try:
                if await self.tick():
                    continue
            except Exception:
                logger.exception("Target attribution queue unavailable")
            await asyncio.sleep(2)

    async def tick(self) -> bool:
        claim = await self.queue.claim(self.runtime.settings.attribution_timeout_seconds + 180)
        if claim is None:
            return False
        try:
            waiting = await self.analyze(claim)
        except asyncio.CancelledError:
            await self.queue.update_claim(
                claim, attribution_owner=None, attribution_due=now_shanghai()
            )
            raise
        except Exception as exc:
            logger.exception("Target attribution batch failed", extra={"target_id": claim.target})
            reason = "analysis_failed"
            if isinstance(exc, AppError) and exc.code == ErrorCode.TARGET_CONTENT_UNRESOLVED:
                reason = "target_unavailable"
            elif isinstance(exc, ValueError):
                reason = "invalid_input_or_report"
            await self.queue.fail(claim, reason)
        else:
            await self.queue.complete(claim, waiting_for_traces=waiting)
        return True

    async def analyze(self, claim: BindingClaim) -> bool:
        workspace = claim.workspace
        target = await self.runtime.targets.get(claim.target, workspace_ids=(workspace,))
        if (
            target is None
            or not target.enabled
            or not target.attribution_package_id
            or target.attribution_generation != claim.generation
        ):
            return False
        snapshot = dict(target.attribution_snapshot or {})
        definition = snapshot.get("definition")
        if "skill" not in snapshot:
            skill = await self.runtime.resolve_bound_skill(target)
            snapshot.update(
                skill=skill.skill_key, skillRevision=skill.revision, hash=skill.content_hash
            )
        if "revision" not in snapshot:
            if definition:
                version, revision = target.default_ref, definition["revision"]
            else:
                resolved = await self.resolver.resolve(
                    object_type=target.object_type,
                    repo_url=target.repo_url,
                    sub_dir=target.sub_dir,
                    version=target.default_ref,
                )
                version, revision = resolved.target_version, resolved.target_revision
            snapshot.update(version=version, revision=revision)
            if not await self.queue.update_claim(claim, attribution_snapshot=snapshot):
                return False
        condition = MatchCondition(
            workspace,
            target.object_type,
            target.object_name,
            snapshot["version"],
            snapshot["revision"],
            datetime(1970, 1, 1, tzinfo=SHANGHAI),
            claim.cutoff,
        )
        association = await self.matcher.associated_sessions(condition)
        if association.pending:
            await self.acquisition.trigger("target_binding")
        match = await self.matcher.potential_cases(condition, association, resolve_policy(None))
        completed = await self.reports.latest_reports(
            workspace,
            target.object_type,
            target.object_name,
            snapshot["revision"],
            tuple(c.bad_case_id for c in match.cases),
            generation=claim.generation,
        )
        pending = [replace(c, included=True) for c in match.cases if c.bad_case_id not in completed]
        if not pending:
            return association.pending > 0
        batch = BindingBatch(
            claim.generation,
            claim.owner,
            workspace,
            target.object_type,
            target.object_name,
            snapshot["version"],
            snapshot["revision"],
            target.repo_url,
            target.sub_dir,
            ENGINE,
            snapshot["skill"],
            snapshot["skillRevision"],
            snapshot["hash"],
            definition=GitDefinitionRef(definition["key"], definition["commit"], definition["path"])
            if definition
            else None,
        )

        async def renew(_: AttributionRunProgress) -> None:
            due = now_shanghai() + timedelta(
                seconds=self.runtime.settings.attribution_timeout_seconds + 180
            )
            if not await self.queue.update_claim(claim, attribution_due=due):
                raise LookupError("target attribution claim was superseded")

        await self.runner.run(batch, pending, False, on_progress=renew)
        return association.pending > 0
