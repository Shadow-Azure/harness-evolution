# Agent Note: Candidate sources belong to the attribution target

Status: proposed

## Problem

A report from A may require analysis of a later C execution. Comparing only the first C occurrence misses repeated executions, and the wizard and automatic batch can select different cases.

## Decision

Confirm source rules during target creation and manage them separately on the target card. Match source type and name, and record the report anchor and matching execution for each rule. Directional rules search the root Session for an execution strictly before or after the anchor. See [#625](https://github.com/Shadow-Azure/harness-evolution/issues/625).

## Alternatives considered

Requiring every source to be a registered target adds repository and version configuration for report-only Skills. Taking the first execution misses C2 in C1, A1, C2.

## Consequences

Overview, wizard and automatic batches need shared matching semantics. Snapshots explain historical selections and reports remain accessible when policy coverage shrinks. Historical scan bounds and triggers remain open design questions.
