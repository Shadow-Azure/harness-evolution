# Agent Note: Evolution Git workspaces and candidate lifecycle

Status: implemented

English | [中文](2026-10-28-git-candidate-workspaces.md)

## Problem

The launch wizard previously created a `preparing` run and a placeholder prepare job only. It neither validated the engine registry nor cloned a frozen version, created a run branch, persisted filtering/clustering/attribution/ranking state, or produced an evaluable candidate. Without those real boundaries, the run detail could only show fixture data and could not prove candidate provenance, remote location, or the fast-forward relationship after acceptance.

## Decision

Launch validates `engine_key` through `EngineFactory.is_registered` before writing and returns `422 ENGINE_INVALID` for an unregistered value. Real prepare reads probes through the frozen run snapshot and reuses the existing query, clustering, and evolution repositories. Full mode first creates an isolated workspace and `evo/{YYYYMMDD}-{run_id}` branch, then uses separate transactions for clustering, cluster confidence, and severity/rank, creates rounds in rank order, and moves the run to `running`; cluster-only preview persists the same read facts without cloning or creating rounds, then enters `completed`.

Git runs only through an argv process boundary with terminal prompts disabled, and every diagnosis is redacted before logging or events. The cache is a mirror at `data/repos/{target_id}`, while the run workspace lives at `data/workspaces/{run_id}`. A mirror whose origin differs from the run's current `repo_url` is rebuilt before use, preventing objects from an old repository from reaching the new remote. Subdirectory, ref, base commit, run branch, clean state, ancestry, and trailers are validated at every publication boundary. `HE_GIT_PUSH=false` suppresses every remote mutation while retaining the local lifecycle. A deterministic placeholder patch is genuinely written and committed; its message fixes problem, analysis, change, trace, and `Harness-Run-Id` trailers. Candidate publication retries immediately up to three times at five-second intervals, persisting `push_failed` before a failure enters `blocked(push)` with the candidate retained.

`HE_GIT_PUSH` is the only public remote-write switch. The composition root passes one workspace instance to prepare, candidate, and retention; prepare-only test injection explicitly disables later candidate scheduling instead of falling back to the default real manager. On Git timeout or task cancellation, the process group is terminated and reaped before a retryable error is returned, so an abandoned push cannot overlap the next attempt. One Git failure classifier maps every push failure to `blocked(push)`, retryable patch/commit failures to `blocked(patch)`, and permanent patch/commit failures to failed while retaining the original `patch`/`commit` error stage.

Git ref namespaces cannot represent `evo/{date}-{run}` simultaneously as a `refs/heads` branch and the prefix of a longer candidate branch. The design's visible candidate ref therefore remains `evo/{date}-{run}/candidate/rN`, but is stored under `refs/tags`; its local work branch uses a hashed name. Acceptance can still make an exact `--force-with-lease` candidate update, switch to the run branch, allow fast-forward only, push without force, and delete the candidate tag. Rejection deletes only the candidate tag and local temporary branch; the run branch and accepted rounds remain unchanged. Accepted and rejected are absorbing states; opposite-direction or repeated terminal mutation returns a stage conflict.

Acceptance is also a replayable state machine. The first attempt amends the evaluated commit; after a failure it reuses only a local or run-branch commit whose tree, `Harness-Evaluated-Commit`, `Harness-Run-Id`, and accepted verdict have been verified, while already-complete remote candidate and run-branch steps are idempotent. After run-branch publication, remote and local candidate deletion are best effort; failures are recorded in `cluster_accepted.payload.cleanupError` and never turn the landed acceptance into blocked. Only failure to restore the run branch during rejection remains blocking.

After the prepare handler finishes, the composition root's terminal lifecycle queues `evolution_advance`, whose production handler publishes the first candidate from the durable turn. A conditional repository update atomically claims one pending turn; a later pending turn cannot overtake an earlier turn that is patching, pushing, evaluating, deciding, or failed, while accepted/rejected unlocks the next turn, and concurrent or repeated advance jobs permit only one publication. The hook first releases the existing sync job lock and then applies workspace retention while preserving active runs. Prepare resumes safely from every cursor gate from 0 through 4; retries do not duplicate turns/candidates or overwrite an accepted branch.

## Alternatives considered

Creating candidates as child branches of the run branch is rejected by Git's file/directory ref conflict. Renaming the visible candidate would break the design, UI, and contract. Allowing force pushes for both run and candidate would make accepted history overwriteable. Putting workspace, patch, and Git validation in callers would let future engines bypass branch/base/clean/trailer boundaries, so the checks remain in the shared Git workspace service.

## Consequences

Prepare, candidate, acceptance, and rejection now have real files, commits, remote refs, durable turns, and event evidence reproducible with a temporary bare remote. The run branch is published when created, and each candidate tag carries the temporary turn object. m5-10 still owns evaluation-completion continuation and terminal decisions, while m5-11 owns automatic backoff and crash recovery. The V1 patch, confidence, and evaluation score are placeholders, while the execution path, state machine, and safety boundary are real.
