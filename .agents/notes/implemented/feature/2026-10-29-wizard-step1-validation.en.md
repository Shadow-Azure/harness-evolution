# Agent Note: Click-time wizard validation and the 409 empty-hit mapping

Status: implemented

English | [中文](2026-10-29-wizard-step1-validation.md)

## Problem

Required-field feedback in wizard step 1 of 「启动自进化」 rests entirely on the disabled state of the "Next" button: the UI never says what is missing or why the click does nothing; the time range is labeled required (`*`) yet does not participate in the disable rule, so the rule contradicts itself. When the form is complete but the query hits zero probes, the `409 NO_PROBES_MATCHED` from `probes/query` is treated like any other error — the internal English message is dumped on the user and the flow dies on step 1, even though zero hits means "the query succeeded but returned nothing", not an error terminal.

## Decision

Keep "Next" always clickable and move validation to click time as field-level feedback: missing target/version/time range marks the input red (`aria-invalid`) with a red missing-field hint below it, each error clears as soon as the field is fixed, and a failing validation sends no request. The frontend maps `probes/query`'s `409 NO_PROBES_MATCHED` to an empty result: advance to step 2, render the no-match empty state with adjust-the-condition guidance, and disable both exit buttons (launch enforces the same rule and would 409 anyway); all other errors keep the step-1 display. The backend contract, OpenAPI, and launch's probe>0 precondition stay untouched — the empty state is the frontend's interpretation of the existing 409, not a new API semantic.

## Alternatives considered

Backend returning `200` with an empty result was rejected: the cross-stack contract and OpenAPI would both change, and launch would still 409, leaving two different "empty result" semantics. Keeping the disabled state with explanatory tooltips was rejected: tooltips are unreliable on touch and keyboard paths, and per-field feedback after a click is what is actionable — the prototype's `wz-query` never had a disabled state either. Keeping the 409 on step 1 with a localized message was rejected: the product requires zero hits to advance to the next step for review and adjustment; staying on step 1 merely swaps English for Chinese while the flow remains stuck.

## Consequences

`NO_PROBES_MATCHED` stops being a pure error code and becomes an "empty-hit signal" the frontend actually consumes; the code string enters a de-facto frontend contract (already in the OpenAPI `ErrorCode` enum, but the frontend now branches on it). Any other surface calling `probes/query` must decide independently whether to reuse the same mapping. Disabling both exits in the empty state is redundant defense — the backend launch would refuse anyway — but it spares users a doomed click. This Note is now synchronized with the implementation.
