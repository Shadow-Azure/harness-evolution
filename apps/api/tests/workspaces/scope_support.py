"""Shared ids and fixture types for the Session workspace-scope tests."""

from dataclasses import dataclass

import httpx

from app.db.base import Database

SESSION_1 = "10000000-0000-4000-8000-000000000001"
SESSION_2 = "10000000-0000-4000-8000-000000000002"
SESSION_3 = "10000000-0000-4000-8000-000000000003"
SESSION_4 = "10000000-0000-4000-8000-000000000004"

CASE_S1_A = "badcase-synthetic-0001"
CASE_S1_B = "badcase-scope-s1-b"
CASE_S2_B = "badcase-synthetic-0002"
CASE_S3_A = "badcase-synthetic-0003"
CASE_S4_DEFAULT = "badcase-synthetic-0004"


@dataclass(frozen=True, slots=True)
class ScopeEnvironment:
    """Seeded two-workspace corpus plus authenticated readers."""

    client: httpx.AsyncClient
    database: Database
    admin: dict[str, str]
    alice: dict[str, str]
    bob: dict[str, str]
    carol: dict[str, str]
    dave: dict[str, str]
    workspace_a: str
    workspace_b: str
