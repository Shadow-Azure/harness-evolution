# Agent Note: Candidate sources belong to the attribution target

Status: implemented

English | [中文](2026-11-26-target-candidate-sources.md)

## Problem

A report from A may require analysis of a later C execution. Comparing only the first C occurrence misses repeated executions, and the wizard and automatic batch can select different cases.

## Decision

Confirm source rules during target creation and manage them separately on the target card. Match source type and name, and record the report anchor and matching execution for each rule. Directional rules search the root Session for an execution strictly before or after the anchor. See [#625](https://github.com/Shadow-Azure/harness-evolution/issues/625).

An existence check on workspace_bad_cases scopes the canonical reports and counts each case once across repeated assignments. Source names are case-sensitive. Historical reports determine the available names and the selected time window determines the self and discovery counts. The catalog label takes precedence, with metaData.label available for direct reports. Reports without anchors remain visible. Repeated source invocations without an identifiable report anchor can satisfy only the same-Session condition.

## Alternatives considered

Requiring every source to be a registered target adds repository and version configuration for report-only Skills. Taking the first execution misses C2 in C1, A1, C2.

## Consequences

The overview, wizard and automatic attribution share a candidate matcher. Target creation stores the binding and policy in one transaction. Changing the rules of a bound target creates a binding generation and scans history up to its cutoff. Each launched run freezes its rules and persists the original report identity and matching coordinates for each candidate. Existing reports remain accessible when a policy narrows.
