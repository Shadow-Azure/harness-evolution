# Project Charter

English | [中文](charter.md)

## Mission

Build a repeatable, auditable loop that lets the harness layer improve continuously on evaluation evidence, while clearly separating real improvement from random fluctuation.

## Scope

### Included

- Harness-layer changes: system prompts, tool definitions, context management, retry and recovery, control flow, approval policy.
- Task sets, graders, trace recording and regression detection.
- Experiment orchestration: proposal, comparative runs, statistical comparison, adoption and rollback.

### Excluded

- Model weight training or fine-tuning.
- Automatic code changes without evaluation evidence.
- Automatic merges, releases or permission changes without human approval.
- Access to production secrets, user-private data or billable resources.

## What counts as evolution

A change may be marked `adopted` only when all conditions hold:

1. The primary metric reaches the pre-declared minimum improvement.
2. Guardrail metrics stay within the allowed regression range.
3. Holdout tasks move in the same direction; tuning-set gains alone do not count.
4. Cost, latency and human-intervention rate stay within budget.
5. The change can roll back through a version or switch.

A single lucky sample is not evolution; a directionally right change below threshold is recorded as `rejected` and kept for reproduction.

## Safety boundaries

- Experiments run in isolated environments and separate branches by default.
- Never read or write production credentials; external services use test accounts and least privilege.
- Every experiment declares run, time and cost limits.
- Automated flows may only propose candidates and never bypass human approval.
- Changes to the evaluator run as separate experiments, never mixed with the harness change under test.

## Experiment protocol

1. State a falsifiable hypothesis.
2. Pin the baseline code version, configuration, task set and random seed.
3. Introduce one primary variable and state its expected effect.
4. Run baseline and treatment under identical conditions.
5. Record all results, including failures and anomalies.
6. Decide by the pre-declared rule and never change thresholds after seeing results.
7. Adopt by updating the baseline; reject by keeping the record and rollback notes.
