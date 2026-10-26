# Agent Note: Evolution Target Configuration and Catalog Boundaries

Status: implemented

English | [中文](2026-10-27-evolution-target-config.md)

## Problem

Evolution target configuration carries credential-sensitive remotes, traversal-sensitive subdirectories, git refs that need immediate feedback, and read-only catalog views. Scattering validation across HTTP routes, building shell commands from remote text, or reparsing payloads for the model catalog would drift security boundaries, make remote calls hard to test, and create duplicate data sources.

## Decision

`service/evolution/targets.py` exclusively normalizes object names, POSIX subdirectories, refs, and HTTPS/SSH/SCP remotes; saves and version reads validate through an injected `GitRemote`. The production adapter lives under `third_party_api/git`, invokes `git ls-remote` with argument arrays, non-interactive stdin, and terminal prompts disabled; POSIX children use an independent session and timeouts terminate the process group before reaping. Every failure maps to `REPO_INVALID` without stderr, credentials, or paths. The configuration collection retains enabled and disabled rows; only catalogs filter `enabled=true`, with bounded concurrency for tag reads. Target writes require admin by HTTP method and path, while reads only require login. Target deletion and the active-run guard share one row-locked transaction; historical runs retain complete target snapshots while the target FK uses `ON DELETE SET NULL`. The model catalog aggregates normalized `agents.model` and never reads JSONL payloads.

## Alternatives considered

Duplicating URL/path/ref validation in routes would let other callers bypass it; interpolating remote text into a shell command would create command injection and complicate child cleanup; filtering disabled rows out of the configuration collection would prevent re-enabling them; aggregating models from payloads would duplicate the normalization source and increase read cost.

## Consequences

Target saves and version listings inherit remote latency under a fixed timeout; this slice neither clones nor caches repositories. The configuration page reads the complete target list, while the future wizard uses the enabled-only catalog. One injected seam tests all git behavior, so future caching or batching replaces the adapter without changing APIs, catalog schemas, or database tables.
