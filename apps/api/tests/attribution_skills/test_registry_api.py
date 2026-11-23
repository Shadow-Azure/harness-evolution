"""Attribution Skill registry, precedence, and immutable revision contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import func, inspect, select, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attribution_skills import AttributionSkillRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.models.domain import attribution_skill_quality_events
from app.db.models.evolution import evolution_run_candidates, evolution_runs, probe_clusters
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.errors import AppError
from app.main import create_app
from app.service.evolution.attribution_skills import AttributionSkillService
from tests.workspaces.helpers import insert_workspace

ADMIN_TEMP_PASSWORD = "attribution-skill-temporary-password"  # noqa: S105
ADMIN_PASSWORD = "attribution-skill-replacement-password"  # noqa: S105


@dataclass(frozen=True, slots=True)
class SkillApiEnvironment:
    """Authenticated client, database, and one workspace target."""

    client: httpx.AsyncClient
    database: Database
    target_id: str


async def _login(client: httpx.AsyncClient) -> None:
    """Complete the required first-login password rotation."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert relogin.status_code == 200
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def skill_api(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[SkillApiEnvironment]:
    """Provide a migrated SQLite app with one configured target."""
    monkeypatch.setattr(
        "app.third_party_api.ai_agent.claude_skill.sandbox_preflight_error", lambda: None
    )
    provider = getattr(request, "param", "fake")
    settings = Settings(
        ai_agent_provider=provider,
        attribution_package_dir=tmp_path / "attribute",
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("attribution-skill-signing-secret-with-length"),
        admin_username="admin",
        admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
    )
    app = create_app(settings)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    try:
        async with app.router.lifespan_context(app):
            await _login(client)
            target = await EvolutionTargetRepository(app.state.database).insert(
                {
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "object_type": "skill",
                    "object_name": "deep-research",
                    "repo_url": "https://git.example.com/deep-research.git",
                    "sub_dir": "skills/deep-research",
                    "default_ref": "main",
                    "validation_project_id": "validation",
                    "test_project_id": "test",
                    "enabled": provider == "fake",
                    "created_by": None,
                },
            )
            yield SkillApiEnvironment(client, app.state.database, target.id)
    finally:
        await client.aclose()


def _base(path: str) -> str:
    """Return a workspace-scoped evolution API path."""
    return f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/evolution/{path}"


async def _create_skill(
    environment: SkillApiEnvironment,
    key: str,
    executor_type: str = "agent_stub",
) -> dict[str, object]:
    """Create one workspace Skill through the public API."""
    response = await environment.client.post(
        _base("attribution-skills"),
        json={
            "skillKey": key,
            "displayName": key,
            "description": f"Instructions for {key}",
            "content": {"instructions": f"Run {key}", "tools": ["trace.read"]},
            "executorType": executor_type,
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


async def _promote(
    environment: SkillApiEnvironment,
    revision_id: object,
) -> dict[str, Any]:
    """Run the Golden Set and accept one passing revision."""
    evaluation = await environment.client.post(
        _base(f"attribution-skills/revisions/{revision_id}/shadow-evaluations"),
    )
    assert evaluation.status_code == 201, evaluation.text
    assert evaluation.json()["report"]["passed"] is True
    accepted = await environment.client.post(
        _base(f"attribution-skills/revisions/{revision_id}/quality-decisions"),
        json={
            "evaluationEventId": evaluation.json()["id"],
            "decision": "accept",
            "reason": "Golden Set and safety gates passed",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["qualityStatus"] == "eligible"
    return cast(dict[str, Any], evaluation.json())


@pytest.mark.asyncio
async def test_resolution_precedence_and_unbind_fallbacks(
    skill_api: SkillApiEnvironment,
) -> None:
    """Target override wins, then workspace default, then protected platform default."""
    listed = await skill_api.client.get(_base("attribution-skills"))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["skillKey"] == "platform-default"

    workspace_skill = await _create_skill(skill_api, "workspace-analysis")
    target_skill = await _create_skill(skill_api, "target-analysis")
    blocked_default = await skill_api.client.put(
        _base("attribution-skill-bindings/default"),
        json={"skillRevisionId": workspace_skill["id"]},
    )
    assert blocked_default.status_code == 409
    assert blocked_default.json()["error"]["code"] == "ATTRIBUTION_QUALITY_GATE_FAILED"
    evaluation = await _promote(skill_api, workspace_skill["id"])
    default_binding = await skill_api.client.put(
        _base("attribution-skill-bindings/default"),
        json={"skillRevisionId": workspace_skill["id"]},
    )
    assert default_binding.status_code == 200
    assert default_binding.json()["source"] == "workspace"
    history = await skill_api.client.get(
        _base(f"attribution-skills/revisions/{workspace_skill['id']}/quality-events"),
    )
    assert history.status_code == 200
    assert [item["eventType"] for item in history.json()["items"]] == [
        "evaluated",
        "accepted",
    ]
    assert history.json()["items"][0]["evaluationHash"] == evaluation["report"]["evaluationHash"]

    target_path = _base(f"targets/{skill_api.target_id}/attribution-skill")
    target_binding = await skill_api.client.put(
        target_path,
        json={"skillRevisionId": target_skill["id"]},
    )
    assert target_binding.status_code == 200
    assert target_binding.json()["skillKey"] == "target-analysis"
    assert target_binding.json()["source"] == "target"

    assert (await skill_api.client.delete(target_path)).status_code == 204
    workspace_fallback = await skill_api.client.get(target_path)
    assert workspace_fallback.json()["skillKey"] == "workspace-analysis"
    assert workspace_fallback.json()["source"] == "workspace"

    assert (
        await skill_api.client.delete(_base("attribution-skill-bindings/default"))
    ).status_code == 204
    platform_fallback = await skill_api.client.get(target_path)
    assert platform_fallback.json()["skillKey"] == "platform-default"
    assert platform_fallback.json()["source"] == "platform"


@pytest.mark.asyncio
async def test_revisions_are_append_only_and_schema_compatible(
    skill_api: SkillApiEnvironment,
) -> None:
    """Publishing appends revisions and rejects duplicate content or schemas."""
    first = await _create_skill(skill_api, "versioned-analysis")
    published = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": {"instructions": "Run revision two", "tools": []},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert published.status_code == 201
    assert published.json()["revision"] == 2
    assert published.json()["contentHash"] != first["contentHash"]

    duplicate = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": first["content"],
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ATTRIBUTION_SKILL_EXISTS"

    incompatible = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": {"instructions": "Unsupported"},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v1",
        },
    )
    assert incompatible.status_code == 422
    assert incompatible.json()["error"]["code"] == "ATTRIBUTION_SKILL_INVALID"


@pytest.mark.asyncio
async def test_platform_skill_cannot_be_disabled(skill_api: SkillApiEnvironment) -> None:
    """The built-in platform definition is referenceable but not workspace-owned."""
    response = await skill_api.client.patch(
        _base("attribution-skills/attribution-skill-platform-default"),
        json={"enabled": False},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTRIBUTION_SKILL_NOT_FOUND"


@pytest.mark.asyncio
async def test_shadow_evaluation_never_writes_the_production_chain(
    skill_api: SkillApiEnvironment,
) -> None:
    """Shadow execution writes only its quality event and leaves runs/reports untouched."""
    skill = await _create_skill(skill_api, "isolated-shadow")

    async def production_counts() -> tuple[int, int, int]:
        async with skill_api.database.session() as session:
            values = []
            for table in (
                evolution_runs,
                evolution_run_candidates,
                probe_clusters,
            ):
                values.append(
                    int(
                        (
                            await session.execute(select(func.count()).select_from(table))
                        ).scalar_one()
                    )
                )
        return cast(tuple[int, int, int], tuple(values))

    before = await production_counts()
    evaluation = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{skill['id']}/shadow-evaluations"),
    )
    after = await production_counts()

    assert evaluation.status_code == 201
    assert evaluation.json()["report"]["passed"] is True
    assert before == after == (0, 0, 0)


@pytest.mark.asyncio
async def test_failed_or_unavailable_engines_cannot_be_promoted(
    skill_api: SkillApiEnvironment,
) -> None:
    """Metric failures and unavailable real Agent executors fail closed."""
    rule = await _create_skill(skill_api, "rule-candidate", "builtin_rule")
    evaluation = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{rule['id']}/shadow-evaluations"),
    )
    assert evaluation.status_code == 201
    assert evaluation.json()["report"]["passed"] is False
    accepted = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{rule['id']}/quality-decisions"),
        json={
            "evaluationEventId": evaluation.json()["id"],
            "decision": "accept",
            "reason": "Must not override failed metrics",
        },
    )
    assert accepted.status_code == 409
    assert accepted.json()["error"]["code"] == "ATTRIBUTION_QUALITY_GATE_FAILED"

    real_agent = await _create_skill(skill_api, "real-agent-candidate", "agent")
    unavailable = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{real_agent['id']}/shadow-evaluations"),
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "ATTRIBUTION_ENGINE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_stale_golden_evaluation_cannot_be_accepted(
    skill_api: SkillApiEnvironment,
) -> None:
    """A report from a different Golden Set hash cannot authorize production default."""
    skill = await _create_skill(skill_api, "stale-golden")
    evaluation = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{skill['id']}/shadow-evaluations"),
    )
    assert evaluation.status_code == 201
    async with skill_api.database.transaction() as session:
        payload = dict(evaluation.json()["report"])
        payload["goldenSetHash"] = "stale-golden-hash"
        await session.execute(
            update(attribution_skill_quality_events)
            .where(attribution_skill_quality_events.c.id == evaluation.json()["id"])
            .values(payload=payload),
        )

    accepted = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{skill['id']}/quality-decisions"),
        json={
            "evaluationEventId": evaluation.json()["id"],
            "decision": "accept",
            "reason": "Must not accept a stale baseline",
        },
    )
    assert accepted.status_code == 409
    assert accepted.json()["error"]["code"] == "ATTRIBUTION_QUALITY_GATE_FAILED"
    assert "stale Golden Set" in accepted.json()["error"]["message"]


@pytest.mark.asyncio
async def test_quality_rejection_and_default_rollback_are_audited(
    skill_api: SkillApiEnvironment,
) -> None:
    """Rejected revisions stay blocked and rollback selects the prior eligible revision."""
    first = await _create_skill(skill_api, "rollback-analysis")
    await _promote(skill_api, first["id"])
    second = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": {"instructions": "Run rollback revision two", "tools": []},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert second.status_code == 201
    second_body = second.json()
    evaluation = await _promote(skill_api, second_body["id"])
    bound = await skill_api.client.put(
        _base("attribution-skill-bindings/default"),
        json={"skillRevisionId": second_body["id"]},
    )
    assert bound.status_code == 200
    assert bound.json()["revision"] == 2

    rolled_back = await skill_api.client.post(
        _base("attribution-skill-bindings/default/rollback"),
        json={"reason": "Observed regression in reviewed shadow diff"},
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["revision"] == 1
    assert rolled_back.json()["qualityStatus"] == "eligible"

    rejected = await skill_api.client.post(
        _base(f"attribution-skills/revisions/{second_body['id']}/quality-decisions"),
        json={
            "evaluationEventId": evaluation["id"],
            "decision": "reject",
            "reason": "Human review rejected the candidate",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["qualityStatus"] == "rejected"
    blocked = await skill_api.client.put(
        _base("attribution-skill-bindings/default"),
        json={"skillRevisionId": second_body["id"]},
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_migration_installs_registry_and_run_snapshot_columns(
    skill_api: SkillApiEnvironment,
) -> None:
    """The migration head exposes all registry tables and immutable run fields."""
    async with skill_api.database.engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        run_columns = await connection.run_sync(
            lambda sync: {
                str(column["name"]) for column in inspect(sync).get_columns("evolution_runs")
            },
        )
        revision_columns = await connection.run_sync(
            lambda sync: {
                str(column["name"])
                for column in inspect(sync).get_columns("attribution_skill_revisions")
            },
        )
    assert {
        "attribution_skills",
        "attribution_skill_revisions",
        "attribution_skill_bindings",
        "attribution_skill_quality_events",
    } <= tables
    assert "quality_status" in revision_columns
    assert {
        "attribution_skill_key",
        "attribution_skill_revision",
        "attribution_skill_content_hash",
    } <= run_columns


@pytest.mark.parametrize("skill_api", ["claude-code"], indirect=True)
async def test_package_mode_keeps_one_explicit_target_binding(
    skill_api: SkillApiEnvironment,
) -> None:
    """Only package IDs are selectable and obsolete mutations leave the target untouched."""
    target = _base(f"targets/{skill_api.target_id}/attribution-skill")
    choices = await skill_api.client.get(_base("attribution-skills"))
    assert choices.status_code == 200
    packages = await skill_api.client.get(
        f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/attribution-skill-packages"
    )
    assert {item["id"] for item in choices.json()["items"]} == {
        item["id"] for item in packages.json()["items"]
    }
    body = {"skillRevisionId": choices.json()["items"][0]["id"]}
    bound = await skill_api.client.put(target, json=body)
    assert bound.status_code == 200
    for response in (
        await skill_api.client.delete(target),
        await skill_api.client.put(_base("attribution-skill-bindings/default"), json=body),
        await skill_api.client.delete(_base("attribution-skill-bindings/default")),
        await skill_api.client.post(
            _base("attribution-skill-bindings/default/rollback"), json={"reason": "test"}
        ),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ATTRIBUTION_SKILL_INVALID"
    assert (await skill_api.client.get(target)).json() == bound.json()


@pytest.mark.asyncio
async def test_registry_revision_api_isolates_workspaces_and_pins_exact_content(
    skill_api: SkillApiEnvironment,
) -> None:
    client = skill_api.client
    first = await _create_skill(skill_api, "workspace-analysis")
    other = await insert_workspace(skill_api.database, name="foreign-registry")
    other_base = f"/api/workspaces/{other}/evolution"
    version_path = f"attribution-skills/revisions/{first['id']}"
    body = {
        "content": {"instructions": "other workspace revision"},
        "executorType": "agent_stub",
        "outputSchemaVersion": "probe-report/v2",
    }
    operations = [
        ("post", f"attribution-skills/{first['skillId']}/revisions", body),
        ("patch", f"attribution-skills/{first['skillId']}", {"enabled": False}),
        ("post", f"{version_path}/shadow-evaluations", None),
        ("get", f"{version_path}/quality-events", None),
        ("put", "attribution-skill-bindings/default", {"skillRevisionId": first["id"]}),
    ]
    for method, path, request in operations:
        denied = await client.request(method, f"{other_base}/{path}", json=request)
        assert denied.status_code == 404, path
        assert denied.json()["error"]["code"] == "ATTRIBUTION_SKILL_NOT_FOUND"
    unchanged = await client.get(_base("attribution-skills"))
    assert any(item["id"] == first["id"] and item["enabled"] for item in unchanged.json()["items"])

    disabled = await client.patch(
        _base(f"attribution-skills/{first['skillId']}"), json={"enabled": False}
    )
    assert disabled.status_code == 204
    registry = AttributionSkillService(AttributionSkillRepository(skill_api.database))
    key = str(first["skillKey"])
    digest = str(first["contentHash"])
    original = await registry.resolve_snapshot(DEFAULT_WORKSPACE_ID, key, 1, digest)
    assert original.content == first["content"] and original.executor_type == "agent_stub"
    for wid, revision, identity in [
        (other, 1, digest),
        (DEFAULT_WORKSPACE_ID, 2, digest),
        (DEFAULT_WORKSPACE_ID, 1, "f" * 64),
    ]:
        with pytest.raises(AppError) as err:
            await registry.resolve_snapshot(wid, key, revision, identity)
        assert err.value.status_code == 409
        assert err.value.code.value == "ATTRIBUTION_SKILL_NOT_FOUND"


@pytest.mark.asyncio
async def test_registry_rejects_unusable_names_content_and_duplicate_skill_keys(
    skill_api: SkillApiEnvironment,
) -> None:
    path = _base("attribution-skills")
    base = {
        "skillKey": "unique-analysis",
        "displayName": "team rules",
        "description": "",
        "content": {"instructions": "inspect"},
        "executorType": "agent_stub",
        "outputSchemaVersion": "probe-report/v2",
    }
    invalid_fields: list[dict[str, object]] = [{"skillKey": "platform-default"}, {"content": {}}]
    for changed in invalid_fields:
        rejected = await skill_api.client.post(path, json={**base, **changed})
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "ATTRIBUTION_SKILL_INVALID"
    first = await skill_api.client.post(path, json=base)
    assert first.status_code == 201
    again = await skill_api.client.post(path, json={**base, "displayName": "replacement"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ATTRIBUTION_SKILL_EXISTS"
    rollback = await skill_api.client.post(
        _base("attribution-skill-bindings/default/rollback"), json={"reason": "restore default"}
    )
    assert rollback.status_code == 409
    assert rollback.json()["error"]["code"] == "ATTRIBUTION_QUALITY_GATE_FAILED"
    items = (await skill_api.client.get(path)).json()["items"]
    assert [s["displayName"] for s in items if s["skillKey"] == "unique-analysis"] == ["team rules"]
