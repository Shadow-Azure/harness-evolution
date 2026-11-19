# M16 Production data directory and deploy writability

English | [中文](m16-milestone.md)

```yaml flow
kind: milestone
id: m16
title: M16 生产数据目录与部署可写性
status: done
github:
  number: 24
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/24
```

## Goals

Let systemd create and authorize the production data directory through `StateDirectory=`, have the deploy pipeline inject an absolute `HE_DATA_DIR`, make `release.sh` validate the path before switching `current`, and have the API probe writability at startup and expose the result on `/api/health`. Routine deploys no longer require logging into the server or running `mkdir` by hand.

## Scope

The unit, bootstrap, release scripts, and config injector under `deploy/`, `.github/workflows/deploy.yml`, the API's `data_dir` resolution, startup write probe and health contract, the production prerequisites in `docs/deployment.*` and the README, plus the matching Agent Note and flow files.

## Acceptance

- The unit carries `StateDirectory=harness-evolution`, and bootstrap idempotently installs or updates it followed by `daemon-reload`; `/var/lib/harness-evolution` is owned by `harness`.
- An empty `vars.HE_DATA_DIR` in the GitHub Environment falls back to the absolute default; relative paths, paths inside the release tree, and unauthorized paths are rejected before deploy while `current` stays unchanged.
- The API resolves the absolute path, creates the directory, and writes a probe at startup; when it is not writable `/api/health` returns 503, the release health check fails, and the deploy rolls back and restores `.env`.
- Local development keeps the `./data` default; tests cover a relative path, a release-directory path, and an unwritable directory.
- The bilingual deployment docs, env template, and README production-prerequisite section stay in sync.

## Non-goals

No root helper or wider deploy sudo permissions, no unit installation in routine deploys, no change to body-hash or target-revision resolution, no data migration tooling, and no frontend UI change.
