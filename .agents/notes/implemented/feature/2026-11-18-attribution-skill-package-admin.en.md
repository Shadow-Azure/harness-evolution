# Agent Note: Separate workspace attribution Skill packages from executable revisions

Status: implemented

English | [中文](2026-11-18-attribution-skill-package-admin.md)

## Problem

Workspace owners need to share a multi-file Skill across targets and inspect exactly which Skill produced each report.

## Decision

Keep uploaded archives in workspace-scoped storage. A target write records one package and durable batch intent together. The worker freezes the resolved object revision and package for the batch. An evolution launch may reuse existing reports or choose a package for a single run. Historical reports retain Skill provenance.

## Alternatives considered

Workspace-wide activation changes unrelated targets. Counting every historical report inflates case counts after recomputation. Deduplicate by case and resolved target revision before grouping by Skill.

## Consequences

The resource library can show and protect bound packages. Background analysis runs independently of downstream clustering. Retry uses the batch generation to skip completed cases.
