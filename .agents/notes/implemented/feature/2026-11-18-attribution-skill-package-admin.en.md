# Agent Note: Separate workspace attribution Skill packages from executable revisions

Status: implemented

English | [中文](2026-11-18-attribution-skill-package-admin.md)

## Problem

Workspace owners need to share a multi-file Skill across targets and inspect exactly which Skill produced each report.

## Decision

Keep uploaded archives in workspace-scoped storage. A target write records one package and durable batch intent together. The worker freezes the object revision. The first Skill content hash recorded for a binding generation fixes the prompt and output writer for both the worker and concurrent wizard launches. A user can choose a different workspace package for a single recomputation. Historical reports retain Skill provenance.

The target overview combines observed-version candidates with completed V2 reports by analysis version and Badcase, including reports whose trace has no version. The sync panel counts trace roots and Badcases in the selected workspace, using each case’s latest completed conclusion. Catalog acquisition and normalization counters cover the platform.

Record visible agent interactions per attempt and link the original Badcase through its input manifest. Keep execution logs separate from validated reports because the Skill can write files inside its working directory.

The report records the actual attribution target in `probe_type`. New reports use `agent` for agents and accept the legacy input `agents`. The platform validates frozen writer output before normalizing the target type and preserves the original reporter type in `from_bad_cases`.

Attribution and clustering share the agent factory and Claude subprocess management. The binding consumer and wizard recomputation share the provider preflight result. Linux Claude probes bubblewrap before claiming work so unavailable dependencies preserve queued generations and their retry budgets. Deployment checks before migration and the API repeats the check as the service account. New snapshots pin the shared model selection and retries reuse the snapshot. A separate `run_skill` capability lets the caller verify file outputs against the frozen inputs and platform writer. Sessions, sanitized diagnostics and usage belong to each call so concurrent Badcases can share a provider instance. Both attribution and the evolution wizard read the Git definition and commit through the same cache-locked reader.

## Alternatives considered

Workspace-wide activation changes unrelated targets. Counting every historical report inflates case counts after recomputation. Deduplicate by case and resolved target revision before grouping by Skill.

## Consequences

The resource library can show and protect bound packages. Background analysis runs independently of downstream clustering. Retry uses the batch generation to skip completed cases.

Each batch stops after three consecutive failures, with delays of 30 and 60 seconds. An expired lease counts as a failure. Polling for an outstanding Session trace uses a separate wait. The target displays the terminal error. After addressing its cause, saving the same binding retries that generation with its snapshot and skips completed Badcases.

Retries in a batch need the inputs first supplied to the model. A per-case manifest pins the redacted prompt, Session evidence version and Skill snapshot. Cases in one Session share evidence. A new batch can use backfilled transcripts, while reuse keeps the original report.

Pin the definition and commit before registering the Git target binding. The analysis version uses the normalized body digest. The archived file uses its raw digest to preserve the complete metadata.
