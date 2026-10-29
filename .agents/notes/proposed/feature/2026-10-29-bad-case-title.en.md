# Agent Note: Add a short-title column to bad_cases

Status: proposed

English | [中文](2026-10-29-bad-case-title.md)

## Problem

The prototype error-detail page renders every problem as two text levels — a short title plus a description body — and both the problem list card and the execution graph problem card use the short title as their primary text; yet `bad_cases`, the `BadCase` contract, and the 05 §9 prototype mapping table carry only the single long `reason` field, so the implementation can only render the whole `reason` as the heading, an unanalyzed list row has no readable title at all, and the real-data error-detail page shows visibly less information than the prototype.

## Decision

Add a `title VARCHAR(255) NOT NULL` short-title column to `bad_cases` as a required field of the external report; narrow `reason` to mean the description body; expose `title` through the `BadCase` / `SessionBadCase` contracts; render `title` as the heading and `reason` as the body on the frontend, and switch the list and graph problem cards to `title` as primary text. The short title is a core display field: it goes into a real column and a real contract, supplied by the upstream system at write time.

## Alternatives considered

A `meta_data.title` convention was rejected: `meta_data` is defined as reporter instrumentation with a non-uniform structure, so parking a core display field inside free-form JSON would make rendering depend on an unreliable convention; truncating `reason` on the frontend was rejected: the cut point is unreliable for mixed CJK/Latin text, a long first sentence still overflows the 150–400px graph-card width clamp, and fidelity suffers.

## Consequences

The upstream problem-reporting system must supply `title` in sync — an external contract change (06 §1 already requires reviewing problem-side schema changes with the upstream); existing `bad_cases` rows are re-imported by the upstream per 06 §1.2 or backfilled once from the first sentence of `reason`; graph problem-card width measuring switches to `title`, producing narrower and more stable cards; `reason` is no longer constrained by heading layout and can carry the full description.
