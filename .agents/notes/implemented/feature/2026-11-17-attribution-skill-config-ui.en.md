# Agent Note: Attribution Skill configuration and run snapshot UI

Status: implemented

English | [中文](2026-11-17-attribution-skill-config-ui.md)

## Problem

The platform already resolved attribution Skills across target, workspace, and platform scopes and froze the selected revision at run launch, but users could not inspect the effective source, switch or roll back a version in target configuration, or verify the Skill actually used before and after launch.

## Decision

Target configuration lets administrators bind a target revision, roll back to an older revision, or remove the binding, while members have read-only access to the effective Skill. Choices are limited to published, enabled, Probe Report V2-compatible revisions that this deployment can execute; the real `agent` executor cannot be newly selected until the internal engine is integrated. The launch wizard shows the resolved source, revision, and executor and states that the run freezes the revision. Run details display only the Skill key, revision, content hash, and engine saved on that run instead of resolving current configuration again.

## Alternatives considered

We did not add a browser editor for Skill bodies because controlled registry publication remains the ownership boundary and this interface only selects versions. We did not resolve the latest effective binding on run detail because it would misrepresent historical execution after configuration changes. We did not offer unavailable `agent` revisions because the public deployment cannot fulfill their execution semantics.

## Consequences

Administrators can bind, roll back, and restore inherited defaults, and every user can verify the attribution engine before and after launch. The frontend uses the real Skill API and shared contracts, with query invalidation refreshing binding changes immediately. Integrating the internal LLM Agent later only requires enabling its executor and exposing capability state; the interaction model remains unchanged.
