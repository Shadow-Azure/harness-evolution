# Agent Note: Add a short-title column to bad_cases

Status: implemented

English | [中文](2026-10-29-bad-case-title.md)

## Problem

The prototype error-detail page renders every problem as two text levels — a short title plus a description body — and both the problem list card and the execution graph problem card use the short title as their primary text; yet `bad_cases` carries only the single long `reason` column, the `BadCase` contract and the 05 §9 prototype mapping table also carry only `reason`, so the implementation can only render the whole `reason` as the heading, an unanalyzed list row has no readable title at all, and the real-data error-detail page shows visibly less information than the prototype. The column names are inconsistent too: every other column of the table carries the `bad_case_` prefix (`bad_case_id` / `bad_case_session_id` / `bad_case_agent_id` / `bad_case_type`), and the body columns of `probe_reports` are prefixed the same way (`probe_description` / `probe_analysis`), leaving `reason` as the only exception.

## Decision

Add a `title VARCHAR(255) NOT NULL` short-title column to `bad_cases` as a required field of the external report, rendered as the error-detail heading and as the primary text of the problem list card and the execution graph problem card. Rename `bad_cases.reason` to `bad_cases.bad_case_description` (`TEXT NOT NULL`): the semantics stay the description body rendered in the detail body block, and the reason for the rename is that the table prefixes its columns with `bad_case_`, matching the naming of `probe_reports.probe_description` / `probe_analysis`. The rename stays inside storage only: the public DTO fields remain `title` and `reason` on `BadCase` / `SessionBadCase`, with `reason` mapped from the `bad_case_description` column, so contracts and frontend do not follow the column name. Existing rows are backfilled once: `bad_case_description` takes the full old `reason` text and `title` takes its first 255 characters; upstream reload (06 §1.2) remains the canonical path, and the backfill only covers databases that were not reloaded. At read time a row still missing `title` degrades to a derived title (the first sentence of the description) and is flagged `degraded`.

## Alternatives considered

A `meta_data.title` convention was rejected: `meta_data` is defined as reporter instrumentation with a non-uniform structure, so parking a core display field inside free-form JSON would make rendering depend on an unreliable convention; keeping the `reason` column name and only adding `title` was rejected: the table would then mix `bad_case_*` and a bare `reason`, forcing readers to infer from two places which column holds the description body, while the rename costs one migration plus one DTO mapping, so the prefix wins; truncating `reason` on the frontend was rejected: the cut point is unreliable for mixed CJK/Latin text, a long first sentence still overflows the 150–400px graph-card width clamp, and fidelity suffers.

## Consequences

The upstream problem-reporting system must supply `title` in sync — an external contract change (06 §1 already requires reviewing problem-side schema changes with the upstream); the column rename needs one alembic migration (batch mode on SQLite), while DTO and frontend field names stay untouched and the mapping lives in one place in the repository; existing `bad_cases` rows are re-imported by the upstream per 06 §1.2 or backfilled once (`title` takes the first 255 characters of the old `reason`), and rows missing `title` at read time fall back to the `degraded` derived title; graph problem-card width measuring switches to `title`, producing narrower and more stable cards; `reason` is no longer constrained by heading layout and can carry the full description.
