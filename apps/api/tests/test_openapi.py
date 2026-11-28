"""OpenAPI snapshot and public schema contracts."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from app.config import DatabaseDialect, Settings
from app.main import create_app
from app.service.evolution.runs import EvolutionRunBlockedStage
from app.service.evolution.stages import RoundStatus

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "packages" / "contracts" / "openapi.json"
API_ROOT = ROOT / "apps" / "api"


def canonicalize(value: Any) -> Any:
    """Return JSON-like data with object keys in a deterministic order."""
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def test_openapi_exposes_implemented_identity_and_error_contracts() -> None:
    """Only implemented health, identity, user, and ticket endpoints are exported."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    components = schema["components"]["schemas"]

    assert set(schema["paths"]) == {
        "/api/health",
        "/api/app-config",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/callback",
        "/api/auth/logout",
        "/api/auth/change-password",
        "/api/auth/me",
        "/api/auth/session",
        "/api/users",
        "/api/events/ticket",
        "/api/events",
        "/api/jobs/{jobId}",
        "/api/sessions",
        "/api/sessions/{sessionId}",
        "/api/sessions/{sessionId}/tree",
        "/api/sessions/{sessionId}/bad-cases",
        "/api/sessions/{sessionId}/probes",
        "/api/bad-cases/{badCaseId}",
        "/api/bad-cases/{badCaseId}/analysis",
        "/api/probes/{probeId}",
        "/api/acquisition/status",
        "/api/acquisition/sync",
        "/api/acquisition/pull",
        "/api/evolution/runs",
        "/api/evolution/runs/{run_id}",
        "/api/evolution/runs/{run_id}/events",
        "/api/evolution/runs/{run_id}/retry",
        "/api/evolution/runs/{run_id}/attribution-jobs",
        "/api/evolution/runs/{run_id}/attribution-jobs/{job_id}/retry",
        "/api/evolution/runs/{run_id}/attribution-jobs/{job_id}/cancel",
        "/api/evolution/runs/{run_id}/steps/range",
        "/api/evolution/runs/{run_id}/steps/sessions",
        "/api/evolution/runs/{run_id}/steps/potential",
        "/api/evolution/runs/{run_id}/steps/attribution",
        "/api/evolution/runs/{run_id}/steps/clusters",
        "/api/evolution/runs/{run_id}/steps/iteration",
        "/api/evolution/runs/{run_id}/steps/final",
        "/api/evolution/probes/query",
        "/api/evolution/cluster-previews",
        "/api/evolution/targets",
        "/api/evolution/targets/{targetId}",
        "/api/evolution/targets/{targetId}/versions",
        "/api/catalogs/targets",
        "/api/catalogs/models",
        "/api/workspaces/{wid}/catalogs/targets",
        "/api/workspaces/{wid}/catalogs/models",
        "/api/workspaces/{wid}/evolution/targets",
        "/api/workspaces/{wid}/evolution/candidate-sources",
        "/api/workspaces/{wid}/evolution/candidate-source-reports",
        "/api/workspaces/{wid}/evolution/targets/{targetId}/candidate-policy",
        "/api/workspaces/{wid}/evolution/targets/{targetId}",
        "/api/workspaces/{wid}/evolution/targets/{targetId}/versions",
        "/api/workspaces/{wid}/evolution/attribution-skills",
        "/api/workspaces/{wid}/evolution/attribution-skills/{skillId}",
        "/api/workspaces/{wid}/evolution/attribution-skills/{skillId}/revisions",
        "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/shadow-evaluations",
        "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/quality-decisions",
        "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/quality-events",
        "/api/workspaces/{wid}/evolution/attribution-skill-bindings/default",
        "/api/workspaces/{wid}/evolution/attribution-skill-bindings/default/rollback",
        "/api/workspaces/{wid}/evolution/targets/{targetId}/attribution-skill",
        "/api/workspaces/{wid}/evolution/runs",
        "/api/workspaces/{wid}/evolution/runs/{run_id}",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/events",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/retry",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs/{job_id}/retry",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs/{job_id}/cancel",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/pause",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/resume",
        "/api/workspaces/{wid}/evolution/runs/{run_id}/steps/{key}",
        "/api/workspaces/{wid}/evolution/cluster-previews",
        "/api/workspaces/{wid}/evolution/preview/sessions",
        "/api/workspaces/{wid}/evolution/preview/potential",
        "/api/workspaces/{wid}/evolution/preview/attribution",
        "/api/workspaces",
        "/api/workspaces/{wid}",
        "/api/workspaces/{wid}/members",
        "/api/workspaces/{wid}/member-candidates",
        "/api/workspaces/{wid}/members/{userId}",
        "/api/workspaces/{wid}/members/self-admin",
        "/api/workspaces/{wid}/credentials",
        "/api/workspaces/{wid}/credentials/{cid}",
        "/api/workspaces/{wid}/attribution-skill-packages",
        "/api/workspaces/{wid}/attribution-skill-packages/{packageId}",
        "/api/workspaces/{wid}/attribution-skill-packages/{packageId}/download",
        "/api/workspaces/{wid}/bad-case-labels",
        "/api/workspaces/{wid}/bad-case-labels/suggestions",
        "/api/workspaces/{wid}/bad-cases",
        "/api/workspaces/{wid}/sessions",
        "/api/workspaces/{wid}/sessions/{sessionId}",
        "/api/workspaces/{wid}/sessions/{sessionId}/tree",
        "/api/workspaces/{wid}/sessions/{sessionId}/bad-cases",
        "/api/workspaces/{wid}/bad-cases/{badCaseId}",
        "/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions",
        "/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions/{attributionId}",
        "/api/workspaces/{wid}/overview/summary",
        "/api/workspaces/{wid}/overview/trend",
        "/api/workspaces/{wid}/overview/sources",
        "/api/workspaces/{wid}/overview/targets",
        "/api/workspaces/{wid}/overview/targets/trend",
        "/api/workspaces/{wid}/overview/targets/cases",
        "/api/workspaces/{wid}/overview/targets/{targetId}/detail",
    }
    assert {
        "HealthResponse",
        "DatabaseHealthResponse",
        "AppConfigResponse",
        "AppConfigBrand",
        "ErrorCode",
        "ErrorResponse",
        "ErrorBody",
        "LoginRequest",
        "LoginResponse",
        "ChangePasswordRequest",
        "CreateUserRequest",
        "PublicUser",
        "SessionPayload",
        "SessionWorkspace",
        "UserListResponse",
        "TicketRequest",
        "EventTicketResponse",
        "JobResponse",
        "SessionStats",
        "SessionListItem",
        "SessionListResponse",
        "SessionEvent",
        "SessionAgent",
        "SessionBadCase",
        "SessionTree",
        "BadCase",
        "BadCaseListResponse",
        "BadCaseAnalysis",
        "ProbeReport",
        "ProbeListResponse",
        "AcquisitionStatusResponse",
        "SyncStatusError",
        "SyncTriggerResponse",
        "EvolutionRunCard",
        "EvolutionRunControl",
        "EvolutionRunList",
        "EvolutionRunTarget",
        "EvolutionRunWindow",
        "EvolutionRunError",
        "EvolutionRunStats",
        "EvolutionRunAttributeStats",
        "EvolutionRunProgress",
        "EvolutionRunFinal",
        "EvolutionStepRange",
        "EvolutionStepSessions",
        "EvolutionStepPotential",
        "EvolutionStepAttribution",
        "EvolutionStepClusters",
        "EvolutionStepIteration",
        "EvolutionStepFinal",
        "EvolutionTarget",
        "EvolutionTargetWrite",
        "EvolutionTargetList",
        "EvolutionTargetVersions",
        "PotentialPolicy",
        "SessionsPreviewRequest",
        "PotentialPreviewRequest",
        "AttributionPreviewRequest",
        "SessionPreviewItem",
        "SessionPreviewSummary",
        "SessionPreviewResult",
        "PotentialPreviewItem",
        "PotentialReasonCounts",
        "PotentialPreviewSummary",
        "PotentialPreviewResult",
        "AttributionPreviewSummary",
        "AttributionPreviewResult",
        "CatalogTarget",
        "CatalogTargets",
        "CatalogModel",
        "CatalogModels",
        "Workspace",
        "WorkspaceAdmin",
        "WorkspaceListResponse",
        "WorkspaceCreateRequest",
        "WorkspaceUpdateRequest",
        "WorkspaceMember",
        "WorkspaceMemberListResponse",
        "WorkspaceMemberCandidate",
        "WorkspaceMemberCandidateListResponse",
        "WorkspaceMemberCreateRequest",
        "WorkspaceMemberUpdateRequest",
        "WorkspaceCredential",
        "WorkspaceCredentialListResponse",
        "WorkspaceCredentialCreated",
        "BadCaseIngest",
        "BadCaseIngestResponse",
        "OverviewSummary",
        "OverviewTotals",
        "OverviewWindow",
        "TrendResponse",
        "TrendBucket",
        "SourceListResponse",
        "SourceRow",
        "OverviewBadCaseListResponse",
        "BadCaseListItem",
        "AttributionItem",
        "AttributionPage",
        "AttributionDetail",
        "AttributionTriggerCompare",
        "TargetOverviewSummary",
        "TargetOverviewItem",
        "TargetOverviewDisabledItem",
        "TargetOverviewListResponse",
        "TargetTrendByTarget",
        "TargetTrendBucket",
        "TargetTrendMeta",
        "TargetTrendResponse",
        "TargetCaseItem",
        "TargetCaseListResponse",
        "TargetDetailTarget",
        "TargetDetailStats",
        "TargetDetailVersion",
        "TargetDetailSource",
        "TargetDetailResponse",
    } <= set(components)
    assert set(components["SessionPreviewItem"]["properties"]) == {
        "sessionId",
        "short",
        "title",
        "objectTriggerAt",
        "badCaseCount",
    }
    assert set(components["AttributionPreviewRequest"]["properties"]) == {
        "targetId",
        "targetType",
        "targetName",
        "targetVersion",
        "from",
        "to",
        "policy",
        "cacheEnabled",
    }
    assert (
        components["SessionsPreviewRequest"]["properties"]["targetVersion"]["anyOf"][0]["maxLength"]
        == 96
    )
    assert (
        "attribution createdAt"
        in components["TargetTrendMeta"]["properties"]["bucketPolicy"]["description"]
    )
    error_body = components["ErrorBody"]
    assert error_body["properties"]["code"]["$ref"] == "#/components/schemas/ErrorCode"
    paths = schema["paths"]
    assert {"200", "401", "403", "422", "429"} <= set(paths["/api/auth/login"]["post"]["responses"])
    assert {"200", "401", "403"} <= set(paths["/api/auth/refresh"]["post"]["responses"])
    assert {"302", "400", "401", "403", "501", "502"} <= set(
        paths["/api/auth/callback"]["get"]["responses"],
    )
    assert {"201", "401", "403", "409", "422"} <= set(paths["/api/users"]["post"]["responses"])
    assert {"200", "401", "403", "422"} <= set(paths["/api/events/ticket"]["post"]["responses"])
    login_401 = paths["/api/auth/login"]["post"]["responses"]["401"]
    assert login_401["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    bearer = schema["components"]["securitySchemes"]["BearerAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"
    protected_operations = [
        ("/api/auth/logout", "post"),
        ("/api/auth/change-password", "post"),
        ("/api/auth/me", "get"),
        ("/api/auth/session", "get"),
        ("/api/users", "get"),
        ("/api/users", "post"),
        ("/api/events/ticket", "post"),
        ("/api/jobs/{jobId}", "get"),
        ("/api/sessions", "get"),
        ("/api/sessions/{sessionId}", "get"),
        ("/api/sessions/{sessionId}/tree", "get"),
        ("/api/sessions/{sessionId}/bad-cases", "get"),
        ("/api/sessions/{sessionId}/probes", "get"),
        ("/api/bad-cases/{badCaseId}", "get"),
        ("/api/bad-cases/{badCaseId}/analysis", "get"),
        ("/api/probes/{probeId}", "get"),
        ("/api/acquisition/status", "get"),
        ("/api/acquisition/sync", "post"),
        ("/api/evolution/runs", "get"),
        ("/api/evolution/runs", "post"),
        ("/api/evolution/runs/{run_id}/steps/range", "get"),
        ("/api/evolution/runs/{run_id}/steps/sessions", "get"),
        ("/api/evolution/runs/{run_id}/steps/potential", "get"),
        ("/api/evolution/runs/{run_id}/steps/attribution", "get"),
        ("/api/evolution/runs/{run_id}/steps/clusters", "get"),
        ("/api/evolution/runs/{run_id}/steps/iteration", "get"),
        ("/api/evolution/runs/{run_id}/steps/final", "get"),
        ("/api/evolution/probes/query", "post"),
        ("/api/evolution/cluster-previews", "post"),
        ("/api/workspaces/{wid}/evolution/runs/{run_id}/pause", "post"),
        ("/api/workspaces/{wid}/evolution/runs/{run_id}/resume", "post"),
        ("/api/workspaces/{wid}/evolution/preview/sessions", "post"),
        ("/api/workspaces/{wid}/evolution/preview/potential", "post"),
        ("/api/workspaces/{wid}/evolution/preview/attribution", "post"),
        ("/api/evolution/targets", "get"),
        ("/api/evolution/targets", "post"),
        ("/api/evolution/targets/{targetId}", "put"),
        ("/api/evolution/targets/{targetId}", "delete"),
        ("/api/evolution/targets/{targetId}/versions", "get"),
        ("/api/catalogs/targets", "get"),
        ("/api/catalogs/models", "get"),
        ("/api/workspaces", "get"),
        ("/api/workspaces", "post"),
        ("/api/workspaces/{wid}", "put"),
        ("/api/workspaces/{wid}/members", "get"),
        ("/api/workspaces/{wid}/members", "post"),
        ("/api/workspaces/{wid}/member-candidates", "get"),
        ("/api/workspaces/{wid}/members/{userId}", "put"),
        ("/api/workspaces/{wid}/members/{userId}", "delete"),
        ("/api/workspaces/{wid}/members/self-admin", "post"),
        ("/api/workspaces/{wid}/credentials", "get"),
        ("/api/workspaces/{wid}/credentials", "post"),
        ("/api/workspaces/{wid}/credentials/{cid}", "delete"),
        ("/api/workspaces/{wid}/overview/summary", "get"),
        ("/api/workspaces/{wid}/overview/trend", "get"),
        ("/api/workspaces/{wid}/overview/sources", "get"),
        ("/api/workspaces/{wid}/overview/targets", "get"),
        ("/api/workspaces/{wid}/overview/targets/trend", "get"),
        ("/api/workspaces/{wid}/overview/targets/cases", "get"),
        ("/api/workspaces/{wid}/overview/targets/{targetId}/detail", "get"),
        ("/api/workspaces/{wid}/bad-cases", "get"),
        ("/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions", "get"),
        ("/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions/{attributionId}", "get"),
    ]
    for path, method in protected_operations:
        assert paths[path][method]["security"] == [{"BearerAuth": []}]
    for path, method in [
        ("/api/health", "get"),
        ("/api/app-config", "get"),
        ("/api/auth/login", "post"),
        ("/api/auth/refresh", "post"),
        ("/api/auth/callback", "get"),
    ]:
        assert "security" not in paths[path][method]
    ingest = paths["/api/workspaces/{wid}/bad-cases"]["post"]
    assert "security" not in ingest
    assert {"200", "201", "401", "403", "404", "409", "422"} <= set(ingest["responses"])
    for status_code in ("200", "201"):
        success = ingest["responses"][status_code]
        assert success["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/BadCaseIngestResponse"
        }
        used_schema = success["headers"]["X-HE-Workspace-Used"]["schema"]
        assert used_schema["type"] == "string"
        assert used_schema["pattern"] == "^[0-9]+$"
    assert ingest["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/BadCaseIngest"
    }
    ingest_properties = set(components["BadCaseIngest"]["properties"])
    assert ingest_properties == {
        "badCaseId",
        "sessionId",
        "badCaseType",
        "objectName",
        "objectType",
        "objectVersion",
        "badCaseAgentId",
        "title",
        "reason",
        "metaData",
        "source",
        "sessionSource",
        "triggerLine",
        "createdAt",
    }
    assert "workspaceId" not in ingest_properties
    assert components["BadCaseIngest"]["additionalProperties"] is False
    assert set(components["BadCaseIngestResponse"]["properties"]) == {
        "badCaseId",
        "workspaceUsed",
    }

    assert {parameter["name"] for parameter in paths["/api/sessions"]["get"]["parameters"]} == {
        "q",
        "status",
        "sort",
        "limit",
    }
    assert set(components["SessionListResponse"]["properties"]) == {
        "items",
        "total",
        "pendingSessions",
    }
    assert set(components["SessionListResponse"]["required"]) == {
        "items",
        "total",
        "pendingSessions",
    }
    legacy_list_parameters = {
        parameter["name"]: parameter for parameter in paths["/api/sessions"]["get"]["parameters"]
    }
    session_list_parameters = {
        parameter["name"]: parameter
        for parameter in paths["/api/workspaces/{wid}/sessions"]["get"]["parameters"]
    }
    assert set(session_list_parameters) == {"wid", "q", "status", "sort", "limit"}
    assert session_list_parameters["limit"]["schema"]["default"] == 10
    assert legacy_list_parameters["limit"]["schema"]["default"] == 100
    assert "Complete root Session ID" in session_list_parameters["q"]["description"]
    assert "description" not in legacy_list_parameters["q"]
    counters = components["SessionListResponse"]["properties"]
    assert "pending roots are excluded" in counters["total"]["description"]
    assert "independent of q and status" in counters["pendingSessions"]["description"]
    session_task_kind = components["SessionAgent"]["properties"]["taskKind"]
    assert session_task_kind["anyOf"][0]["enum"] == [
        "in_process_teammate",
        "forked_skill",
    ]
    for path in ("/api/sessions/{sessionId}", "/api/sessions/{sessionId}/tree"):
        validation = paths[path]["get"]["responses"]["422"]
        assert validation["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    target_collection = paths["/api/evolution/targets"]
    assert paths["/api/evolution/runs"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EvolutionRunList"}
    step_not_ready = paths["/api/evolution/runs/{run_id}/steps/range"]["get"]["responses"]["404"]
    assert step_not_ready["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    run_card = components["EvolutionRunCard"]
    assert set(run_card["properties"]) == {
        "runId",
        "controlState",
        "pauseRequestedAt",
        "pausedAt",
        "pausedBy",
        "canPause",
        "canResume",
        "title",
        "mode",
        "target",
        "targets",
        "window",
        "models",
        "policy",
        "cacheEnabled",
        "createdBy",
        "createdAt",
        "status",
        "error",
        "stats",
        "progress",
        "final",
        "degraded",
    }
    assert run_card["properties"]["controlState"]["enum"] == [
        "running",
        "pause_requested",
        "paused",
    ]
    for action in ("pause", "resume"):
        responses = paths[f"/api/workspaces/{{wid}}/evolution/runs/{{run_id}}/{action}"]["post"][
            "responses"
        ]
        assert {"200", "401", "403", "404", "409"} <= set(responses)
        assert responses["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/EvolutionRunControl"
        }
    assert components["EvolutionRunWindow"]["properties"]["from"]["anyOf"][0]["format"] == ("date")
    detail_schema = components["EvolutionRunDetail"]
    assert detail_schema["properties"]["evalStatus"]["enum"] == [
        "pending",
        "evaluating",
        "completed",
        "failed",
        "timeout",
    ]
    assert detail_schema["properties"]["blockedStage"]["anyOf"][0]["enum"] == [
        "patch",
        "push",
        "eval",
        "attribution",
    ]
    assert components["EvolutionRunWorkspace"]["properties"]["pushStatus"]["enum"] == [
        "pending",
        "pushing",
        "succeeded",
        "failed",
        "skipped",
    ]
    assert components["StepRound"]["properties"]["status"]["enum"] == [
        "pending",
        "patching",
        "pushing",
        "evaluating",
        "deciding",
        "accepted",
        "rejected",
        "skipped",
        "failed",
    ]
    assert components["StepRoundPush"]["properties"]["status"]["enum"] == [
        "pending",
        "pushing",
        "succeeded",
        "skipped",
        "failed",
    ]
    assert components["StepRoundEval"]["properties"]["status"]["enum"] == [
        "pending",
        "evaluating",
        "completed",
        "failed",
        "timeout",
    ]
    assert target_collection["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EvolutionTargetList"}
    assert target_collection["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EvolutionTargetWrite"
    }
    assert target_collection["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EvolutionTarget"}
    target_item = paths["/api/evolution/targets/{targetId}"]
    assert target_item["put"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EvolutionTarget"
    }
    assert set(target_item["delete"]["responses"]) >= {
        "204",
        "401",
        "403",
        "404",
        "409",
        "422",
    }
    assert paths["/api/evolution/targets/{targetId}/versions"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {"$ref": "#/components/schemas/EvolutionTargetVersions"}
    assert paths["/api/catalogs/targets"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/CatalogTargets"}
    assert paths["/api/catalogs/models"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/CatalogModels"}
    case_parameters = paths["/api/bad-cases/{badCaseId}"]["get"]["parameters"]
    analysis_parameters = paths["/api/bad-cases/{badCaseId}/analysis"]["get"]["parameters"]
    assert {parameter["name"] for parameter in case_parameters} == {
        "badCaseId",
        "sessionId",
    }
    assert {parameter["name"] for parameter in analysis_parameters} == {
        "badCaseId",
        "sessionId",
    }
    for parameter in [*case_parameters, *analysis_parameters]:
        if parameter["name"] == "sessionId":
            assert parameter["schema"]["anyOf"][0]["minLength"] == 1
    analysis_schema = components["BadCaseAnalysis"]
    assert analysis_schema["discriminator"] == {
        "mapping": {
            "unanalyzed": "#/components/schemas/UnanalyzedBadCaseAnalysis",
            "analyzed_nonissue": "#/components/schemas/NonIssueBadCaseAnalysis",
            "analyzed_issue": "#/components/schemas/IssueBadCaseAnalysis",
        },
        "propertyName": "status",
    }
    assert [item["$ref"] for item in analysis_schema["oneOf"]] == [
        "#/components/schemas/UnanalyzedBadCaseAnalysis",
        "#/components/schemas/NonIssueBadCaseAnalysis",
        "#/components/schemas/IssueBadCaseAnalysis",
    ]
    issue_result = components["IssueAnalysisResult"]["properties"]
    assert set(issue_result) == {"summary"}
    non_issue_result = components["NonIssueAnalysisResult"]["properties"]
    assert set(non_issue_result) == {"reason", "reasoning"}
    assert "409" in paths["/api/bad-cases/{badCaseId}"]["get"]["responses"]
    assert paths["/api/bad-cases/{badCaseId}"]["get"]["responses"]["409"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
    overview_parameters = {
        parameter["name"]: parameter
        for parameter in paths["/api/workspaces/{wid}/overview/summary"]["get"]["parameters"]
    }
    assert set(overview_parameters) == {"wid", "from", "to", "range", "objects"}
    assert overview_parameters["from"]["schema"]["anyOf"][0]["format"] == "date"
    assert overview_parameters["to"]["schema"]["anyOf"][0]["format"] == "date"
    assert overview_parameters["range"]["schema"]["enum"] == [7, 30, 90]
    assert overview_parameters["objects"]["schema"]["anyOf"][0]["type"] == "array"
    assert "comma-separated" in overview_parameters["objects"]["description"]
    trend_parameters = {
        parameter["name"]: parameter
        for parameter in paths["/api/workspaces/{wid}/overview/trend"]["get"]["parameters"]
    }
    assert trend_parameters["grain"]["schema"]["default"] == "day"
    assert trend_parameters["grain"]["schema"]["enum"] == ["day", "week", "month"]
    assert "effective grain" in trend_parameters["grain"]["description"]
    list_parameters = {
        parameter["name"]: parameter
        for parameter in paths["/api/workspaces/{wid}/bad-cases"]["get"]["parameters"]
    }
    assert set(list_parameters) == {
        "wid",
        "from",
        "to",
        "range",
        "allTime",
        "objects",
        "badCaseType",
        "page",
        "pageSize",
    }
    assert list_parameters["page"]["schema"]["default"] == 1
    assert list_parameters["allTime"]["schema"]["default"] is False
    assert list_parameters["allTime"]["schema"]["type"] == "boolean"
    assert list_parameters["range"]["schema"]["enum"] == [7, 30, 90]
    assert list_parameters["pageSize"]["schema"]["default"] == 8
    assert list_parameters["pageSize"]["schema"]["maximum"] == 50
    assert list_parameters["badCaseType"]["schema"]["default"] == "all"
    for path in (
        "/api/workspaces/{wid}/overview/summary",
        "/api/workspaces/{wid}/overview/trend",
        "/api/workspaces/{wid}/overview/sources",
        "/api/workspaces/{wid}/bad-cases",
    ):
        assert {"401", "403", "404", "422"} <= set(paths[path]["get"]["responses"])
        assert paths[path]["get"]["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    assert paths["/api/workspaces/{wid}/bad-cases"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/OverviewBadCaseListResponse"}
    assert paths["/api/workspaces/{wid}/overview/summary"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/OverviewSummary"}
    assert paths["/api/workspaces/{wid}/overview/trend"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/TrendResponse"}
    assert paths["/api/workspaces/{wid}/overview/sources"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/SourceListResponse"}
    assert components["OverviewTotals"]["properties"]["self"]["type"] == "integer"
    assert components["OverviewTotals"]["properties"]["discovery"]["type"] == "integer"
    assert set(components["OverviewTotals"]["properties"]) == {
        "badCases",
        "self",
        "discovery",
        "sessions",
        "sources",
        "quota",
        "used",
    }
    assert (
        "without a normalized trace"
        in (components["OverviewTotals"]["properties"]["sessions"]["description"])
    )
    assert components["TrendResponse"]["properties"]["grain"]["enum"] == [
        "day",
        "week",
        "month",
    ]
    assert set(components["TrendBucket"]["properties"]) == {
        "bucket",
        "label",
        "self",
        "discovery",
        "total",
    }
    assert set(components["SourceRow"]["properties"]) == {
        "object",
        "total",
        "self",
        "discovery",
        "sessions",
    }
    assert set(components["BadCaseListItem"]["properties"]) == {
        "badCaseId",
        "sessionId",
        "objectName",
        "badCaseType",
        "badCaseTypeLabel",
        "title",
        "triggerAt",
        "triggerLine",
        "createdAt",
        "attributionCount",
        "syncStatus",
        "sessionReady",
        "lastError",
        "retryable",
        "nextRetryAt",
    }
    assert components["BadCaseTraceStatus"]["enum"] == [
        "ready",
        "pending",
        "syncing",
        "failed",
        "unavailable",
    ]
    assert (
        "temporarily equals createdAt"
        in components["BadCaseListItem"]["properties"]["triggerAt"]["description"]
    )
    trigger_line = components["BadCaseListItem"]["properties"]["triggerLine"]
    assert trigger_line["anyOf"] == [{"minimum": 0, "type": "integer"}, {"type": "null"}]
    assert "log line" in trigger_line["description"]
    assert "createdAt" in trigger_line["description"]
    error_codes = components["ErrorCode"]["enum"]
    assert {
        "BAD_CASE_NOT_FOUND",
        "BAD_CASE_SESSION_PENDING",
        "BAD_CASE_SESSION_UNAVAILABLE",
        "BAD_CASE_SESSION_MISMATCH",
        "PROBE_NOT_FOUND",
        "WORKSPACE_EXISTS",
        "MEMBER_EXISTS",
        "MEMBER_NOT_FOUND",
        "ROLE_INVALID",
        "ROLE_LOCKED",
        "QUOTA_INVALID",
        "CREDENTIAL_NOT_FOUND",
        "CREDENTIAL_INVALID",
        "CREDENTIAL_LIMIT",
        "QUOTA_EXCEEDED",
        "BAD_CASE_ID_CONFLICT",
        "WINDOW_INVALID",
        "GRAIN_INVALID",
        "OBJECT_FILTER_TOO_LARGE",
        "POLICY_INVALID",
        "NO_ASSOCIATED_SESSIONS",
        "NO_POTENTIAL_MATCHED",
    } <= set(error_codes)
    assert "/api/sessions/{sessionId}/timeline" not in paths
    trigger_responses = paths["/api/acquisition/sync"]["post"]["responses"]
    assert {"200", "202", "401", "403"} <= set(trigger_responses)
    assert trigger_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SyncTriggerResponse"
    }


def test_evolution_status_aliases_reject_non_design_states() -> None:
    """Runtime validation rejects stages and round states absent from the design."""
    blocked_stage = cast(
        TypeAdapter[EvolutionRunBlockedStage],
        TypeAdapter(cast(Any, EvolutionRunBlockedStage)),
    )
    round_status = cast(
        TypeAdapter[RoundStatus],
        TypeAdapter(cast(Any, RoundStatus)),
    )

    assert blocked_stage.validate_python("patch") == "patch"
    assert round_status.validate_python("evaluating") == "evaluating"

    with pytest.raises(ValidationError):
        blocked_stage.validate_python("prepare")
    with pytest.raises(ValidationError):
        round_status.validate_python("blocked")


def test_checked_in_openapi_snapshot_is_current() -> None:
    """FastAPI schema drift fails until the deterministic snapshot is regenerated."""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()

    assert canonicalize(actual) == expected


def test_identity_time_and_secret_configuration_matches_design() -> None:
    """Deployment names and defaults preserve the authoritative auth contract."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, _env_file=None)  # type: ignore[call-arg]

    assert settings.access_token_ttl_min == 30
    assert settings.refresh_token_ttl_days == 14
    assert settings.access_ttl_seconds == 1_800
    assert settings.refresh_ttl_seconds == 1_209_600
    assert settings.event_ticket_ttl_seconds == 60
    assert settings.sse_heartbeat_seconds == 15
    assert settings.sse_queue_capacity == 100
    assert settings.event_replay_limit == 500
    assert settings.sync_interval_seconds == 60
    assert settings.sync_lock_ttl_seconds == 1_800


def test_openapi_export_ignores_service_environment() -> None:
    """Canonical snapshots cannot drift because of local HE_* overrides."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("HE_")}
    environment.update(
        {
            "HE_VERSION": "environment-drift",
            "HE_PHASE": "live",
            "HE_DOCS_ENABLED": "true",
            "PYTHONIOENCODING": "ascii",
            "PATH": os.environ["PATH"],
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py"],
        cwd=API_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    assert json.loads(result.stdout)["info"]["version"] == "0.1.0"
    assert "§4.2.1" in result.stdout
