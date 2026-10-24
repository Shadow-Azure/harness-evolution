# Agent Note: SQLite/MySQL database boundary

Status: implemented

English | [中文](2026-10-25-database-boundary.md)

## Problem

Identity, trace normalization and evolution all need persistence, yet their environments differ: production uses MySQL 8 while tests and fast local runs need SQLite. Business code that creates engines directly or embeds dialect SQL mixes local success with production failure; separate dialect migration trees make schemas impossible to compare.

## Decision

- A `Database` protocol owns connection lifecycle, read sessions, write transactions and health; `create_database()` is the sole `HE_DB_DIALECT` dispatch point.
- SQLite enables WAL, foreign keys, busy timeout and NORMAL synchronous mode; MySQL uses pooling, pre-ping, recycling and a `+08:00` session timezone.
- Alembic uses one migration tree and an async URL, with batch mode for SQLite table changes; domain tables arrive in later issues while this stage establishes an empty baseline.
- `/api/health` reports both API and database state; connection failure does not prevent process startup and instead returns HTTP 503 with a sanitized database summary. Server logs retain only the phase, dialect and exception type, never raw driver text, URLs, hosts or paths.
- The `-m mysql` repository contract reuses the same SQLAlchemy expressions as SQLite; CI's MySQL 8 service must execute that suite.

## Alternatives considered

- Maintain separate SQLite and MySQL repositories: business queries would be duplicated and quickly drift; rejected.
- Terminate FastAPI when startup cannot connect: operators would see only a dead process and could not distinguish API from database failure through health; rejected.
- Maintain one Alembic tree per dialect: schema comparison and environment switching become more expensive; rejected.
- Run only the SQLite suite: MySQL index, dialect and connection-setting failures would remain invisible; rejected.

## Consequences

- CI carries both a fast SQLite lane and a MySQL service lane, increasing time and infrastructure dependencies while making cross-dialect regressions visible before merge.
- Later features depend only on `Database` and repository interfaces; dialect or connection policy changes stay under `apps/api/app/db/`.
- The health contract includes `version` and `db`, letting the web app distinguish an unreachable API from a reachable API with an unhealthy database.
- The empty migration creates no domain tables; later schemas evolve through new revisions and cannot modify the published baseline.
