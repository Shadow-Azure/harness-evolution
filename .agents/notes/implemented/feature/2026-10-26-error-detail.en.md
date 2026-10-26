# Agent Note: Error Details and Attribution Tabs

Status: implemented

English | [中文](2026-10-26-error-detail.md)

## Problem

Problem cards and attribution APIs already expose real data, but users need a refreshable and shareable error-detail entry point without scattering description, attribution reasoning, filtered flow, and cross-session ownership across pages.

## Decision

`/sessions/:sid/errors?case=<id>&tab=desc|attr` is the source of truth for error details. The page always combines a problem sidebar, a filtered Agent flow, and bottom description/attribution tabs. `case` and `tab` restore from the URL; selecting all errors removes both. The flow keeps only the selected problem anchor around the original Agent/Skill structure. The bad-case API remains authoritative for cross-session ownership through `409 BAD_CASE_SESSION_MISMATCH`; 404 and transport failures degrade at page level. That conflict is shown only by the blocking page state, without a duplicate global toast; other 409 conflicts not handled by a page retain the global notice.

Compact error cards in the sidebar follow the prototype's two-line structure: sequence number, real problem ID, and reason on the first line; state, reported object, and the attribution-report deep link for analyzed issues on the second. The report link shows the first eight characters of the real probe ID and opens the attribution tab. The flow retains layout diagnosis data for logs and tests without exposing raw diagnosis codes in the product UI; fatal diagnosis conditions that produce zero nodes show a readable unavailable state. The description shows the real ID, state, summary, key facts, and related object, while degraded data uses user-facing copy without machine diagnosis codes. Attribution always orders conclusion, category or non-issue reason, located object, problem description, and reasoning. Unanalyzed, failure, and missing-probe states are independent. Markdown permits safe links and content but never executes external HTML.

## Alternatives considered

- Embedding details in a Session overview dialog: rejected because it cannot carry long reasoning or a shareable deep link.
- Inferring Session ownership from caseId in the browser: rejected because it duplicates the external contract and can expose cross-session data.
- Rendering the full graph while only highlighting a problem: rejected because it obscures the selected evidence chain and diverges from the prototype.

## Consequences

Error details survive refresh, history navigation, and new-window links without pretending to generate AI attribution. The page depends on both bad-case and Agent-tree reads; new tabs, fields, or anchor rules must update the URL parser, component tests, and real-Chrome E2E together. The external three-table boundary remains read-only.
