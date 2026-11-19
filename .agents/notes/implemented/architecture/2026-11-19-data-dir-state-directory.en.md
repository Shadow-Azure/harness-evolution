# Agent Note: Production data directory owned by systemd StateDirectory

Status: implemented

English | [中文](2026-11-19-data-dir-state-directory.md)

## Problem

After a skill version is selected, the launch wizard reads `SKILL.md` and computes a body hash; before running any git command the server creates the `data_dir/target-content` cache directory. When `HE_DATA_DIR` is unset, `data_dir` defaults to `data`, which resolves relative to systemd's `WorkingDirectory=/opt/harness/current/api` inside the release tree. Production runs as `User=harness`, the release tree belongs to `deploy` and is replaced wholesale on each release, so `harness` cannot `mkdir`; the `OSError` is mapped to `content_unavailable` and the first wizard step fails.

This is not a repository URL, subdirectory, tag, or network problem. It is a deployment gap exposed by the first server-side need for a persistent writable directory: MySQL deployments never go through SQLite's `data_dir.mkdir`, and production never ran an evolution run that writes `data/repos`. An unwritable release tree is a design fact; the data directory must live outside it and be managed by systemd.

## Decision

- `deploy/harness-api.service` declares `StateDirectory=harness-evolution`, so systemd creates `/var/lib/harness-evolution` and chowns it to `harness` at every start; bootstrap idempotently installs or updates the unit as root, runs `daemon-reload`, creates the directory, and restarts once. Unit installation is per-environment initialization, not a routine deploy, and deploy's sudo permissions do not grow.
- Production `HE_DATA_DIR` must be an absolute path, defaulting to `/var/lib/harness-evolution/data`; API configuration rejects relative paths in production. Local development keeps `./data`, resolved relative to the process cwd.
- `Deploy` reads the GitHub Environment `vars.HE_DATA_DIR` (empty uses the absolute default) and writes it atomically into `.env` through the generalized `inject-config.py`, alongside the evaluation config, after backing up to `.env.bak.<sha>`.
- Before switching `current`, `release.sh` validates that the path is non-empty, absolute, free of whitespace/newlines and `..`, outside `current` and `releases`, and owned by `harness:harness` or covered by the unit's `StateDirectory=`. It exits immediately on failure while the current release keeps serving. Every failure path restores the pre-injection `.env`; a failed probe restores `.env` before switching back to the previous release and restarting.
- At startup the API resolves the absolute path, runs `mkdir(parents=True, exist_ok=True)`, and creates and deletes a write probe. Only `data: {ok}` is exposed on `/api/health`; an unwritable directory returns 503, which fails the deploy probe and rolls back. Startup does not crash on an unwritable directory, avoiding a crash loop with no health response. The path and error details stay in logs.
- A path change is a data migration: `target-content`, `repos`, and `workspaces` do not follow, so the docs require stopping the service and moving the directories before changing the config.

## Alternatives considered

- **Option B: root helper plus sudoers so `release.sh` installs the unit on every deploy.** Rejected: the unit source sits in a deploy-writable directory, so installing it verbatim would extend root trust to the deploy pipeline; unit changes are rare and not worth that trust surface.
- **Anchor relative paths to `$STATE_DIRECTORY` inside the app.** Rejected: it hides a configuration error and forks production semantics from local development, so a wrong path would go unnoticed before deploy.
- **Only a static `release.sh` check.** Rejected: the deploy user cannot prove that `harness` can write; read-only mounts, a full disk, and ACL denials are invisible, and the check runs after `.env` was already written.
- **Only the health write probe.** Rejected: a bad `.env` would stay in the shared file, so the old release would read it after rollback; without restoring `.env` first, the rollback itself may fail to start.
- **Fail fast and exit at startup.** Rejected: it is safe only together with `.env` restoration; otherwise a bad value prevents both the new and the old release from starting. The health 503 already makes the pipeline roll back while preserving a health response for diagnosis.

## Consequences

- `/api/health` gains `data.ok`, and the `HealthResponse` contract and generated types follow; monitoring and the release probe can see data-directory writability.
- An existing environment needs one root action: rerun the updated bootstrap, or install the unit in `/etc/systemd/system`, run `daemon-reload`, and restart. Routine deploys are automatic afterwards.
- `.env` gains `HE_DATA_DIR` (injected by the pipeline); a manual production start without an absolute path fails configuration validation. A path change needs a manual data migration.
- A failed deploy restores `.env.bak.<sha>`; at most 5 backups are kept, matching the release retention policy.
- The decision does not change body-hash or target-revision resolution semantics; it only guarantees that the local write directory they need is in the right place and writable.
