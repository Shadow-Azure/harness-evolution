"""Dialect-neutral persistence for evolution runs, clusters, rounds, and finals."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import CursorResult

from app.db.base import Database
from app.db.models.evolution import (
    ClusterWrite,
    EvolutionFinalRecord,
    EvolutionRoundRecord,
    EvolutionRunRecord,
    ProbeClusterRecord,
    evolution_finals,
    evolution_rounds,
    evolution_runs,
    probe_cluster_probes,
    probe_clusters,
    record_from_evolution_final,
    record_from_evolution_round,
    record_from_evolution_run,
    record_from_probe_cluster,
)
from app.service.evolution.state import StageConflict, validate_transition
from app.utils.ids import new_id
from app.utils.time import now_shanghai

TYPE_IMPACT: dict[str, float] = {
    "error": 9.0,
    "prompt": 7.0,
    "model": 5.0,
}


class EvolutionRepository:
    """Persist durable evolution state through one database boundary."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database."""
        self._database = database

    async def create_run(self, values: Mapping[str, Any]) -> EvolutionRunRecord:
        """Insert one run with immutable configuration snapshots."""
        now = now_shanghai()
        payload = {
            "id": values.get("id", new_id()),
            "title": values["title"],
            "mode": values["mode"],
            "engine_key": values["engine_key"],
            "eval_config": deepcopy(dict(values["eval_config"])),
            "target_config_id": values["target_config_id"],
            "target_type": values["target_type"],
            "target_name": values["target_name"],
            "target_version": values["target_version"],
            "repo_url": values["repo_url"],
            "sub_dir": values["sub_dir"],
            "repo_path": values.get("repo_path"),
            "base_ref": values.get("base_ref"),
            "base_commit": values.get("base_commit"),
            "branch_name": values.get("branch_name"),
            "workspace_path": values.get("workspace_path"),
            "remote_name": values.get("remote_name", "origin"),
            "push_status": values.get("push_status", "pending"),
            "pushed_at": values.get("pushed_at"),
            "push_error": values.get("push_error"),
            "window_from": values.get("window_from"),
            "window_to": values.get("window_to"),
            "models": deepcopy(list(values.get("models", []))),
            "status": values.get("status", "preparing"),
            "blocked_stage": values.get("blocked_stage"),
            "retry_attempts": values.get("retry_attempts", 0),
            "next_retry_at": values.get("next_retry_at"),
            "eval_status": values.get("eval_status", "pending"),
            "error_stage": values.get("error_stage"),
            "error_message": values.get("error_message"),
            "error_at": values.get("error_at"),
            "progress_unit": values.get("progress_unit", 0),
            "stats": deepcopy(dict(values.get("stats", {}))),
            "created_by": values.get("created_by"),
            "created_at": values.get("created_at", now),
            "finished_at": values.get("finished_at"),
        }
        async with self._database.transaction() as session:
            await session.execute(insert(evolution_runs).values(**payload))
        created = await self.get_run(str(payload["id"]))
        if created is None:
            raise RuntimeError("created evolution run disappeared")
        return created

    async def get_run(self, run_id: str) -> EvolutionRunRecord | None:
        """Return one run by stable id."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(evolution_runs).where(evolution_runs.c.id == run_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return record_from_evolution_run(cast(Mapping[str, Any], row)) if row is not None else None

    async def advance_unit(
        self,
        run_id: str,
        *,
        expected: int,
        target: int,
        cluster_count: int,
    ) -> EvolutionRunRecord:
        """Advance one cursor unit only when the persisted cursor still matches."""
        validate_transition(expected, target, cluster_count)
        async with self._database.transaction() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(evolution_runs)
                    .where(
                        evolution_runs.c.id == run_id,
                        evolution_runs.c.progress_unit == expected,
                    )
                    .values(progress_unit=target),
                ),
            )
        if result.rowcount != 1:
            current = await self.get_run(run_id)
            if current is None:
                raise LookupError("evolution run not found")
            raise StageConflict(
                status_code=409,
                current=current.progress_unit,
                target=target,
                reason="stale cursor",
            )
        advanced = await self.get_run(run_id)
        if advanced is None:
            raise LookupError("evolution run not found")
        return advanced

    async def replace_clusters(
        self,
        run_id: str,
        clusters: Sequence[ClusterWrite],
    ) -> tuple[ProbeClusterRecord, ...]:
        """Replace one run's complete cluster snapshot in one transaction."""
        now = now_shanghai()
        cluster_rows: list[dict[str, Any]] = []
        link_rows: list[dict[str, str]] = []
        for seq, cluster in enumerate(clusters, start=1):
            cluster_id = new_id()
            cluster_rows.append(
                {
                    "probe_cluster_id": cluster_id,
                    "run_id": run_id,
                    "seq": seq,
                    "probe_cluster_description": cluster.description,
                    "probe_cluster_type": cluster.type,
                    "confidence": None,
                    "impact": TYPE_IMPACT[cluster.type],
                    "severity": None,
                    "rank": None,
                    "created_at": now,
                },
            )
            link_rows.extend(
                {
                    "probe_cluster_id": cluster_id,
                    "probe_id": probe_id,
                }
                for probe_id in cluster.probes
            )

        async with self._database.transaction() as session:
            run_exists = (
                await session.execute(
                    select(evolution_runs.c.id).where(evolution_runs.c.id == run_id),
                )
            ).scalar_one_or_none()
            if run_exists is None:
                raise LookupError("evolution run not found")
            existing_ids = list(
                (
                    await session.execute(
                        select(probe_clusters.c.probe_cluster_id).where(
                            probe_clusters.c.run_id == run_id,
                        ),
                    )
                ).scalars(),
            )
            if existing_ids:
                await session.execute(
                    delete(probe_cluster_probes).where(
                        probe_cluster_probes.c.probe_cluster_id.in_(existing_ids),
                    ),
                )
            await session.execute(
                delete(probe_clusters).where(probe_clusters.c.run_id == run_id),
            )
            if cluster_rows:
                await session.execute(insert(probe_clusters), cluster_rows)
            if link_rows:
                await session.execute(insert(probe_cluster_probes), link_rows)
        return await self.list_clusters(run_id)

    async def list_clusters(self, run_id: str) -> tuple[ProbeClusterRecord, ...]:
        """Return one run's clusters in creation order."""
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(probe_clusters)
                        .where(probe_clusters.c.run_id == run_id)
                        .order_by(probe_clusters.c.seq),
                    )
                )
                .mappings()
                .all()
            )
        return tuple(record_from_probe_cluster(cast(Mapping[str, Any], row)) for row in rows)

    async def insert_rounds(self, rounds: Sequence[Mapping[str, Any]]) -> None:
        """Insert the pending execution rounds for one prepared run."""
        if not rounds:
            return
        values = []
        for round_ in rounds:
            values.append(
                {
                    "id": round_.get("id", new_id()),
                    "run_id": round_["run_id"],
                    "probe_cluster_id": round_["probe_cluster_id"],
                    "seq": round_["seq"],
                    "status": round_.get("status", "pending"),
                    "started_at": round_.get("started_at"),
                    "finished_at": round_.get("finished_at"),
                    "duration_ms": round_.get("duration_ms"),
                    "error_message": round_.get("error_message"),
                    "patch": deepcopy(round_.get("patch")),
                    "candidate_ref": round_.get("candidate_ref"),
                    "candidate_commit": round_.get("candidate_commit"),
                    "candidate_message": round_.get("candidate_message"),
                    "push_status": round_.get("push_status", "pending"),
                    "push_attempts": round_.get("push_attempts", 0),
                    "pushed_at": round_.get("pushed_at"),
                    "push_error": round_.get("push_error"),
                    "eval_external_id": round_.get("eval_external_id"),
                    "eval_status": round_.get("eval_status", "pending"),
                    "eval_attempts": round_.get("eval_attempts", 0),
                    "eval_next_poll_at": round_.get("eval_next_poll_at"),
                    "eval_started_at": round_.get("eval_started_at"),
                    "eval_finished_at": round_.get("eval_finished_at"),
                    "eval_current": round_.get("eval_current"),
                    "eval_candidate": round_.get("eval_candidate"),
                    "eval_result": deepcopy(round_.get("eval_result")),
                    "eval_error": round_.get("eval_error"),
                    "accepted": round_.get("accepted", False),
                    "commit_hash": round_.get("commit_hash"),
                    "commit_message": round_.get("commit_message"),
                },
            )
        async with self._database.transaction() as session:
            await session.execute(insert(evolution_rounds), values)

    async def list_rounds(self, run_id: str) -> tuple[EvolutionRoundRecord, ...]:
        """Return one run's execution rounds in sequence order."""
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(evolution_rounds)
                        .where(evolution_rounds.c.run_id == run_id)
                        .order_by(evolution_rounds.c.seq),
                    )
                )
                .mappings()
                .all()
            )
        return tuple(record_from_evolution_round(cast(Mapping[str, Any], row)) for row in rows)

    async def write_final(self, values: Mapping[str, Any]) -> EvolutionFinalRecord:
        """Insert or replace a run's single final-evaluation row."""
        run_id = str(values["run_id"])
        payload = {
            "best_version": values["best_version"],
            "verdict": values["verdict"],
            "best_score": values["best_score"],
            "init_score": values["init_score"],
            "metrics": deepcopy(values["metrics"]),
        }
        async with self._database.transaction() as session:
            existing = (
                await session.execute(
                    select(evolution_finals.c.run_id).where(
                        evolution_finals.c.run_id == run_id,
                    ),
                )
            ).scalar_one_or_none()
            if existing is None:
                await session.execute(
                    insert(evolution_finals).values(run_id=run_id, **payload),
                )
            else:
                await session.execute(
                    update(evolution_finals)
                    .where(evolution_finals.c.run_id == run_id)
                    .values(**payload),
                )
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(evolution_finals).where(
                            evolution_finals.c.run_id == run_id,
                        ),
                    )
                )
                .mappings()
                .one()
            )
        return record_from_evolution_final(cast(Mapping[str, Any], row))
