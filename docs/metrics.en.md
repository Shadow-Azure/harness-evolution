# Metric Definitions

English | [中文](metrics.md)

## Primary metric

Every experiment declares one primary metric, task success rate by default:

- **Task success rate**: tasks passing the grader / total tasks.
- **Pass@k**: share of tasks succeeding at least once across k independent attempts; suited to high-variance tasks.

## Guardrail metrics

- **Regressions**: tasks that pass on baseline and fail on treatment.
- **Steps and tool calls**: whether the flow became verbose.
- **Tokens and cost**: average per-task consumption and total budget.
- **Latency**: end-to-end and key-stage duration.
- **Human-intervention rate**: corrections or approvals required.
- **Stability**: result variance across seeds or repeated runs.

## Recording requirements

Every run records at least:

- harness version and configuration hash
- task-set version
- model and inference parameters
- random seed
- start and end time
- per-task results and full traces
- aggregate metrics and anomaly notes

Changing a metric definition creates a new version and references it in experiment records, so batches are never compared directly across definitions.
