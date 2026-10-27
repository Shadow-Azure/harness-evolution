# Agent Note: Evolution Git workspaces and candidate lifecycle

Status: implemented

English | [中文](2026-10-28-git-candidate-workspaces.md)

## Problem

The launch wizard previously created a `preparing` run and a placeholder prepare job only. It neither validated the engine registry nor cloned a frozen version, created a run branch, persisted filtering/clustering/attribution/ranking state, or produced an evaluable candidate. Without those real boundaries, the run detail could only show fixture data and could not prove candidate provenance, remote location, or the fast-forward relationship after acceptance.

## Decision

Launch validates `engine_key` through `EngineFactory.is_registered` before writing and returns `422 ENGINE_INVALID` for an unregistered value. Real prepare reads probes through the frozen run snapshot and reuses the existing query, clustering, and evolution repositories. Full mode first creates an isolated workspace and `evo/{YYYYMMDD}-{run_id}` branch, then uses separate transactions for clustering, cluster confidence, and severity/rank, creates rounds in rank order, and moves the run to `running`; cluster-only preview persists the same read facts without cloning or creating rounds, then enters `completed`.

Git runs only through an argv process boundary with terminal prompts disabled, and every diagnosis is redacted before logging or events. The cache is a mirror at `data/repos/{target_id}`, while the run workspace lives at `data/workspaces/{run_id}`. A mirror whose origin differs from the run's current `repo_url` is rebuilt before use, preventing objects from an old repository from reaching the new remote. Subdirectory, ref, base commit, run branch, clean state, ancestry, and trailers are validated at every publication boundary. `HE_GIT_PUSH=false` suppresses every remote mutation while retaining the local lifecycle. A deterministic placeholder patch is genuinely written and committed; its message fixes problem, analysis, change, trace, and `Harness-Run-Id` trailers. Candidate publication retries immediately up to three times at five-second intervals, persisting `push_failed` before a failure enters `blocked(push)` with the candidate retained.

Git ref namespaces cannot represent `evo/{date}-{run}` simultaneously as a `refs/heads` branch and the prefix of a longer candidate branch. The design's visible candidate ref therefore remains `evo/{date}-{run}/candidate/rN`, but is stored under `refs/tags`; its local work branch uses a hashed name. Acceptance can still make an exact `--force-with-lease` candidate update, switch to the run branch, allow fast-forward only, push without force, and delete the candidate tag. Rejection deletes only the candidate tag and local temporary branch; the run branch and accepted rounds remain unchanged. Accepted and rejected are absorbing states; opposite-direction or repeated terminal mutation returns a stage conflict.

After the prepare handler finishes, the composition root's terminal lifecycle queues `evolution_advance`, whose production handler publishes the first candidate from the durable turn. The hook first releases the existing sync job lock and then applies workspace retention while preserving active runs. Prepare resumes safely from every cursor gate from 0 through 4; retries do not duplicate turns/candidates or overwrite an accepted branch.

## Alternatives considered

Creating candidates as child branches of the run branch is rejected by Git's file/directory ref conflict. Renaming the visible candidate would break the design, UI, and contract. Allowing force pushes for both run and candidate would make accepted history overwriteable. Putting workspace, patch, and Git validation in callers would let future engines bypass branch/base/clean/trailer boundaries, so the checks remain in the shared Git workspace service.

## Consequences

Prepare, candidate, acceptance, and rejection now have real files, commits, remote refs, durable turns, and event evidence reproducible with a temporary bare remote. The run branch is published when created, and each candidate tag carries the temporary turn object. m5-10 still owns evaluation-completion continuation and terminal decisions, while m5-11 owns automatic backoff and crash recovery. The V1 patch, confidence, and evaluation score are placeholders, while the execution path, state machine, and safety boundary are real.
